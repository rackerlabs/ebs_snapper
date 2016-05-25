# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for doing EBS snapshots."""

from __future__ import print_function
import json
import logging
import datetime
import dateutil

import boto3
from ebs_snapper_lambda_v2 import utils, dynamo


LOG = logging.getLogger(__name__)


def perform_fanout_all_regions():
    """For every region, run the supplied function"""
    # get regions with instances running or stopped
    regions = utils.get_regions(must_contain_instances=True)
    for region in regions:
        perform_fanout_by_region(region=region)


def perform_fanout_by_region(region):
    """For a specific region, run this function for every matching instance"""

    sns_topic = utils.get_topic_arn('CreateSnapshotTopic')

    # get all configurations, so we can filter instances
    configurations = dynamo.fetch_configurations()
    if len(configurations) <= 0:
        LOG.warn('No EBS snapshot configurations were found for region %s', region)
        LOG.warn('No new snapshots will be created for region %s', region)

    # for every configuration
    for config in configurations:

        # if it's missing the match section, ignore it
        if not utils.validate_snapshot_settings(config):
            continue

        # build a boto3 filter to describe instances with
        configuration_matches = config['match']

        filters = utils.convert_configurations_to_boto_filter(configuration_matches)

        # if we ended up with no boto3 filters, we bail so we don't snapshot everything
        if len(filters) <= 0:
            LOG.warn('Could not convert configuration match to a filter: %s',
                     configuration_matches)
            continue

        # send a message for each instance in this region, to
        # evaluate if it should create a snapshot
        send_message_instances(
            region=region,
            sns_topic=sns_topic,
            configuration_snapshot=config,
            filters=filters)


def send_message_instances(region, sns_topic, configuration_snapshot, filters):
    """Send message to all instance_id's in region. Filters must be in the boto3 format."""

    filters.append({'Name': 'instance-state-name',
                    'Values': ['running', 'stopped']})

    client = boto3.client('ec2', region_name=region)
    instances = client.describe_instances(Filters=filters)

    for reservation in instances.get('Reservations', []):
        for instance in reservation.get('Instances', []):
            send_fanout_message(
                instance_id=instance['InstanceId'],
                region=region,
                topic_arn=sns_topic,
                snapshot_settings=configuration_snapshot)


def send_fanout_message(instance_id, region, topic_arn, snapshot_settings):
    """Publish an SNS message to topic_arn that specifies an instance and region to review"""
    message = json.dumps({'instance_id': instance_id,
                          'region': region,
                          'settings': snapshot_settings})

    LOG.info('send_fanout_message: %s', message)

    utils.sns_publish(TopicArn=topic_arn, Message=message)


def perform_snapshot(region, instance, snapshot_settings):
    """Check the region and instance, and see if we should take any snapshots"""
    LOG.info('Reviewing snapshots in region %s on instance %s', region, instance)

    # parse out snapshot settings
    retention, frequency = utils.parse_snapshot_settings(snapshot_settings)

    # grab the data about this instance id
    instance_data = utils.get_instance(instance, region)

    for dev in instance_data.get('BlockDeviceMappings', []):
        LOG.debug('Considering device %s', dev)
        volume_id = dev['Ebs']['VolumeId']

        # find snapshots
        recent = utils.most_recent_snapshot(volume_id, region)
        now = datetime.datetime.now(dateutil.tz.tzutc())

        # if newest snapshot time + frequency < now(), do a snapshot
        if recent is None:
            LOG.info('Last snapshot for volume %s was not found', volume_id)
            LOG.info('Next snapshot for volume %s should be due now', volume_id)
        else:
            LOG.info('Last snapshot for volume %s was at %s', volume_id, recent['StartTime'])
            LOG.info('Next snapshot for volume %s should be due at %s',
                     volume_id,
                     (recent['StartTime'] + frequency))

        # snapshot due?
        should_perform_snapshot = recent is None or (recent['StartTime'] + frequency) < now
        if should_perform_snapshot:
            LOG.info('Performing snapshot for %s', volume_id)
        else:
            LOG.info('NOT Performing snapshot for %s', volume_id)
            continue

        # perform actual snapshot and create tag: retention + now() as a Y-M-D
        delete_on_dt = now + retention
        delete_on = delete_on_dt.strftime('%Y-%m-%d')
        utils.snapshot_and_tag(volume_id, delete_on, region)
