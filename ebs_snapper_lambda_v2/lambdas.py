# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module containing AWS lambda functions."""

from __future__ import print_function

import json
from functools import partial

from ebs_snapper_lambda_v2 import utils, snapshot, clean


def lambda_fanout_snapshot(event, context):
    """Fanout SNS messages to trigger snapshots when called by AWS Lambda."""
    # get SNS ready and get the topic we care about for snapshot creation
    sns_topic = utils.get_topic_arn('CreateSnapshotTopic')

    # prepare a function that can fanout to a particular ARN
    send_snapshot_fanout_arn = partial(snapshot.send_fanout_message, topic_arn=sns_topic)

    # for every region and every instance, send to this function
    snapshot.perform_fanout_all_regions(send_snapshot_fanout_arn)

    print('Function lambda_fanout_snapshot completed')


def lambda_fanout_clean(event, context):
    """Fanout SNS messages to cleanup snapshots when called by AWS Lambda."""
    sns_topic = utils.get_topic_arn('CleanSnapshotTopic')

    # prepare a function that can fanout to a particular ARN
    send_clean_fanout_arn = partial(clean.send_fanout_message, topic_arn=sns_topic)

    # for every region, send to this function
    clean.perform_fanout_all_regions(send_clean_fanout_arn)

    print('Function lambda_fanout_clean completed')


def lambda_snapshot(event, context):
    """Snapshot a single instance when called by AWS Lambda."""
    records = event.get('Records')
    for record in records:
        sns = record.get('Sns')
        if not sns:
            continue
        message = sns.get('Message')
        message_json = json.loads(message)

        # call the snapshot perform method
        snapshot.perform_snapshot(message_json['region'], message_json['instance_id'])

    print('Function lambda_snapshot completed')


def lambda_clean(event, context):
    """Clean up a single region when called by AWS Lambda."""
    records = event.get('Records')
    for record in records:
        sns = record.get('Sns')
        if not sns:
            continue
        message = sns.get('Message')
        message_json = json.loads(message)

        # call the snapshot cleanup method
        clean.clean_snapshot(message_json['region'])

    print('Function lambda_clean completed')
