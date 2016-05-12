# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for doing EBS snapshots."""

from __future__ import print_function
import json
from functools import partial

import boto3
from ebs_snapper_lambda_v2 import utils


def perform_fanout_all_regions(message_function):
    """For every region, run the supplied function"""
    # get regions with instances running or stopped
    regions = utils.get_regions(must_contain_instances=True)
    for region in regions:
        perform_fanout_by_region(message_function, region)


def perform_fanout_by_region(message_function, region):
    """For a specific region, run this function for every instance"""
    # build a partial function for sending the fanout message to a specific region
    regional_message_function = partial(message_function, region=region)

    # apply it to all running or stopped instances in the region
    utils.apply_instances(region=region, func=regional_message_function)


def send_fanout_message(instance_id, region, topic_arn):
    """Publish an SNS message to topic_arn that specifies an instance and region to review"""
    print('send_fanout_message for region {}, instance {} to {}'
          .format(region, instance_id, topic_arn))
    sns_client = boto3.client('sns', region_name=region)
    message = json.dumps({'instance_id': instance_id, 'region': region})
    sns_client.publish(TopicArn=topic_arn, Message=message)


def print_fanout_message(instance_id, region):
    """Instead of SNS, just print the message we would have sent"""
    message = json.dumps({'instance_id': instance_id, 'region': region})
    print('send_fanout_message: {}'.format(message))


def perform_snapshot(region, instance):
    """Check the region and instance, and see if we should take any snapshots"""
    print('Perform a snapshot of region {} on instance {}'.format(region, instance))
