# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for cleaning up snapshots."""

from __future__ import print_function
import json
import logging
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
