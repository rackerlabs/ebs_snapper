# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for doing EBS snapshots."""

from __future__ import print_function
import json
import logging

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
        if 'match' not in config or 'snapshot' not in config:
            LOG.warn(
                'Configuration is missing a match/snapshot, will not use it for snapshots: %s',
                str(config))
            continue

        # build a boto3 filter to describe instances with
        configuration_matches = config['match']
        configuration_snapshot = config['snapshot']

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
            configuration_snapshot=configuration_snapshot,
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
    LOG.debug('send_fanout_message for region %s, instance %s to %s',
              region, instance_id, topic_arn)

    message = json.dumps({'instance_id': instance_id,
                          'region': region,
                          'settings': snapshot_settings})
    utils.sns_publish(TopicArn=topic_arn, Message=message)


def perform_snapshot(region, instance, snapshot_settings):
    """Check the region and instance, and see if we should take any snapshots"""
    LOG.info('Perform a snapshot of region %s on instance %s', region, instance)
