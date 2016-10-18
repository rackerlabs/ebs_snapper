# -*- coding: utf-8 -*-
#
# Copyright 2016 Rackspace US, Inc.
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
"""Module containing AWS lambda functions."""

from __future__ import print_function

import json
import logging

from ebs_snapper import snapshot, clean

LOG = logging.getLogger()


def lambda_fanout_snapshot(event, context):
    """Fanout SNS messages to trigger snapshots when called by AWS Lambda."""

    # baseline logging for lambda
    logging.basicConfig(level=logging.INFO)
    LOG.setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)

    # for every region and every instance, send to this function
    snapshot.perform_fanout_all_regions(context)

    LOG.info('Function lambda_fanout_snapshot completed')


def lambda_fanout_clean(event, context):
    """Fanout SNS messages to cleanup snapshots when called by AWS Lambda."""

    # baseline logging for lambda
    logging.basicConfig(level=logging.INFO)
    LOG.setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)

    # for every region, send to this function
    clean.perform_fanout_all_regions(context)

    LOG.info('Function lambda_fanout_clean completed')


def lambda_snapshot(event, context):
    """Snapshot a single instance when called by AWS Lambda."""

    # baseline logging for lambda
    logging.basicConfig(level=logging.INFO)
    LOG.setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)

    if not (event and event.get('Records')):
        LOG.warn('lambda_snapshot must be invoked from an SNS topic: %s', str(event))
        return

    records = event.get('Records')
    for record in records:
        sns = record.get('Sns')
        if not sns:
            LOG.warn('lambda_snapshot missing an SNS section: %s', str(event))
            continue

        message = sns.get('Message')
        if not message:
            LOG.warn('lambda_snapshot missing a message section: %s', str(event))
            continue

        message_json = json.loads(message)

        if 'region' not in message_json:
            LOG.warn('lambda_snapshot missing specific keys: %s', str(event))
            continue

        # call the snapshot perform method
        snapshot.perform_snapshot(
            context,
            message_json['region'])

        LOG.info('Function lambda_snapshot completed')


def lambda_clean(event, context):
    """Clean up a single region when called by AWS Lambda."""

    # baseline logging for lambda
    logging.basicConfig(level=logging.INFO)
    LOG.setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)

    if not (event and event.get('Records')):
        LOG.warn('lambda_clean must be invoked from an SNS topic')
        return

    records = event.get('Records')
    for record in records:
        sns = record.get('Sns')
        if not sns:
            LOG.warn('lambda_clean missing an SNS section: %s', str(event))
            continue

        message = sns.get('Message')
        if not message:
            LOG.warn('lambda_clean missing a message section: %s', str(event))
            continue

        message_json = json.loads(message)

        if 'region' not in message_json:
            LOG.warn('lambda_clean missing specific keys: %s', str(event))
            continue

        # call the snapshot cleanup method
        clean.clean_snapshot(context, message_json['region'])

    LOG.info('Function lambda_clean completed')
