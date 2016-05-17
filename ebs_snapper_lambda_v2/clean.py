# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for cleaning up snapshots."""

from __future__ import print_function
import json
import boto3
from ebs_snapper_lambda_v2 import utils


def perform_fanout_all_regions(message_function):
    """For every region, run the supplied function"""
    # get regions, regardless of instances
    regions = utils.get_regions(must_contain_instances=False)
    for region in regions:
        message_function(region=region)


def send_fanout_message(region, topic_arn):
    """Publish an SNS message to topic_arn that specifies a region to review snapshots on"""
    print('send_fanout_message for region {} to {}'.format(region, topic_arn))
    sns_client = boto3.client('sns', region_name=region)
    message = json.dumps({'region': region})
    sns_client.publish(TopicArn=topic_arn, Message=message)


def print_fanout_message(region):
    """Instead of SNS, just print the message we would have sent"""
    message = json.dumps({'region': region})
    print('send_fanout_message: {}'.format(message))


def clean_snapshot(region):
    """Check the region see if we should clean up any snapshots"""
    print('Clean up snapshots in region {}'.format(region))
