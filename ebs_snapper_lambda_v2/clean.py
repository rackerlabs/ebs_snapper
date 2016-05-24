# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for cleaning up snapshots."""

from __future__ import print_function
import datetime
from datetime import timedelta
import json
import logging
import boto3
from ebs_snapper_lambda_v2 import utils

LOG = logging.getLogger(__name__)


def perform_fanout_all_regions():
    """For every region, run the supplied function"""
    # get regions, regardless of instances
    sns_topic = utils.get_topic_arn('CleanSnapshotTopic')
    LOG.info('perform_fanout_all_regions using SNS topic %s', sns_topic)

    regions = utils.get_regions(must_contain_instances=False)
    for region in regions:
        send_fanout_message(region=region, topic_arn=sns_topic)


def send_fanout_message(region, topic_arn):
    """Publish an SNS message to topic_arn that specifies a region to review snapshots on"""
    LOG.info('send_fanout_message for region %s to %s', region, topic_arn)
    message = json.dumps({'region': region})
    utils.sns_publish(TopicArn=topic_arn, Message=message)


def clean_snapshot(region):
    """Check the region see if we should clean up any snapshots"""
    LOG.info('clean_snapshot in region %s', region)

    owner_ids = utils.get_owner_id()
    LOG.info('Filtering snapshots to clean by owner id %s', owner_ids)

    delete_on = datetime.date.today()
    for i in range(0, 10):
        clean_snapshots_tagged(delete_on + timedelta(days=-i), owner_ids, region)


def clean_snapshots_tagged(delete_on, owner_ids, region):
    """Remove snapshots where DeleteOn tag is delete_on datetime object"""
    ec2 = boto3.client('ec2', region_name=region)
    filters = [
        {'Name': 'tag-key', 'Values': ['DeleteOn']},
        {'Name': 'tag-value', 'Values': [delete_on.strftime('%Y-%m-%d')]},
    ]
    LOG.info("ec2.describe_snapshots with filters %s", filters)
    snapshot_response = ec2.describe_snapshots(OwnerIds=owner_ids, Filters=filters)

    if 'Snapshots' not in snapshot_response or len(snapshot_response['Snapshots']) <= 0:
        LOG.warn('No snapshots were found using owners=%s, filters=%s',
                 owner_ids,
                 filters)
        return

    # TODO: handle minimum setting
    # minimum_snaps = snapshot_settings['minimum']

    for snap in snapshot_response['Snapshots']:
        LOG.info('Deleting snapshot %s from %s', snap['SnapshotId'], region)
        utils.delete_snapshot(snap['SnapshotId'], region)
