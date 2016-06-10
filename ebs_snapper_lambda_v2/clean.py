# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for cleaning up snapshots."""

from __future__ import print_function
import datetime
from datetime import timedelta
import json
import logging
import boto3
from ebs_snapper_lambda_v2 import utils, dynamo

LOG = logging.getLogger(__name__)


def perform_fanout_all_regions():
    """For every region, run the supplied function"""
    # get regions, regardless of instances
    sns_topic = utils.get_topic_arn('CleanSnapshotTopic')
    LOG.info('perform_fanout_all_regions using SNS topic %s', sns_topic)

    regions = utils.get_regions(must_contain_instances=True)
    for region in regions:
        send_fanout_message(region=region, topic_arn=sns_topic)


def send_fanout_message(region, topic_arn):
    """Publish an SNS message to topic_arn that specifies a region to review snapshots on"""
    message = json.dumps({'region': region})
    LOG.info('send_fanout_message: %s', message)

    utils.sns_publish(TopicArn=topic_arn, Message=message)


def clean_snapshot(region):
    """Check the region see if we should clean up any snapshots"""
    LOG.info('clean_snapshot in region %s', region)

    owner_ids = utils.get_owner_id(region)
    LOG.info('Filtering snapshots to clean by owner id %s', owner_ids)

    LOG.info('Fetching all possible configuration rules from DynamoDB')
    configurations = dynamo.list_configurations()

    deleted_count = 0
    delete_on = datetime.date.today()
    for i in range(0, 10):
        deleted_count += clean_snapshots_tagged(
            delete_on + timedelta(days=-i),
            owner_ids,
            region,
            configurations)

    if deleted_count <= 0:
        LOG.warn('No snapshots were cleaned up for the entire region %s', region)


def clean_snapshots_tagged(delete_on, owner_ids, region, configurations, default_min_snaps=5):
    """Remove snapshots where DeleteOn tag is delete_on datetime object"""
    ec2 = boto3.client('ec2', region_name=region)
    filters = [
        {'Name': 'tag-key', 'Values': ['DeleteOn']},
        {'Name': 'tag-value', 'Values': [delete_on.strftime('%Y-%m-%d')]},
    ]
    LOG.info("ec2.describe_snapshots with filters %s", filters)
    snapshot_response = ec2.describe_snapshots(OwnerIds=owner_ids, Filters=filters)
    LOG.info("ec2.describe_snapshots fin")

    deleted_count = 0
    if 'Snapshots' not in snapshot_response or len(snapshot_response['Snapshots']) <= 0:
        LOG.debug('No snapshots were found using owners=%s, filters=%s',
                  owner_ids,
                  filters)
        return deleted_count

    for snap in snapshot_response['Snapshots']:
        # attempt to identify the instance this applies to, so we can check minimums
        try:
            snapshot_volume = snap['VolumeId']
            volume_instance = utils.get_instance_by_volume(snapshot_volume, region)

            # minimum required
            if volume_instance is None:
                minimum_snaps = default_min_snaps
            else:
                snapshot_settings = utils.get_snapshot_settings_by_instance(
                    volume_instance, configurations, region)
                minimum_snaps = snapshot_settings['snapshot']['minimum']

            # current number of snapshots
            no_snaps = utils.count_snapshots(snapshot_volume, region)

            # if we have less than the minimum, don't delete this one
            if no_snaps < minimum_snaps:
                LOG.warn('Not deleting snapshot %s from %s', snap['SnapshotId'], region)
                LOG.warn('Only %s snapshots exist, below minimum of %s', no_snaps, minimum_snaps)
                continue

        except:
            # if we couldn't figure out a minimum of snapshots,
            # don't clean this up -- these could be orphaned snapshots
            LOG.warn('Not deleting snapshot %s from %s, error encountered',
                     snap['SnapshotId'], region)
            continue

        LOG.warn('Deleting snapshot %s from %s', snap['SnapshotId'], region)
        utils.delete_snapshot(snap['SnapshotId'], region)
        deleted_count += 1

    return deleted_count
