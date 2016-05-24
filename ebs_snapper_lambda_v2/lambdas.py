# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module containing AWS lambda functions."""

from __future__ import print_function

import json
import logging

from ebs_snapper_lambda_v2 import snapshot, clean

LOG = logging.getLogger(__name__)

# baseline logging for lambda
logging.basicConfig(level=logging.INFO)


def lambda_fanout_snapshot(event, context):
    """Fanout SNS messages to trigger snapshots when called by AWS Lambda."""

    # for every region and every instance, send to this function
    snapshot.perform_fanout_all_regions()

    LOG.info('Function lambda_fanout_snapshot completed')


def lambda_fanout_clean(event, context):
    """Fanout SNS messages to cleanup snapshots when called by AWS Lambda."""

    # for every region, send to this function
    clean.perform_fanout_all_regions()

    LOG.info('Function lambda_fanout_clean completed')


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
        snapshot.perform_snapshot(
            message_json['region'],
            message_json['instance_id'],
            message_json['settings'])

    LOG.info('Function lambda_snapshot completed')


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

    LOG.info('Function lambda_clean completed')
