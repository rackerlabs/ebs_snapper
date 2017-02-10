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
"""Module for doing EBS snapshots."""

from __future__ import print_function
from time import sleep
import json
import logging
from datetime import timedelta
import datetime
import dateutil

from ebs_snapper import utils, dynamo, timeout_check


LOG = logging.getLogger()


def perform_fanout_all_regions(context, cli=False):
    """For every region, run the supplied function"""

    sns_topic = utils.get_topic_arn('CreateSnapshotTopic')
    LOG.debug('perform_fanout_all_regions using SNS topic %s', sns_topic)

    # get regions with instances running or stopped
    regions = utils.get_regions(must_contain_instances=True)
    for region in regions:
        sleep(5)  # API rate limiting help

        send_fanout_message(
            context=context,
            region=region,
            sns_topic=sns_topic,
            cli=cli)


def send_fanout_message(context, region, sns_topic, cli=False):
    """Send message to all instance_id's in region. Filters must be in the boto3 format."""

    message = json.dumps({'region': region})
    LOG.debug('send_fanout_message: %s', message)

    if cli:
        perform_snapshot(context, region)
    else:
        utils.sns_publish(TopicArn=sns_topic, Message=message)


def perform_snapshot(context, region, installed_region='us-east-1'):
    """Check the region and instance, and see if we should take any snapshots"""
    LOG.info('Reviewing snapshots in region %s', region)

    # fetch these, in case we need to figure out what applies to an instance
    configurations = dynamo.list_configurations(context, installed_region)
    LOG.debug('Fetched all possible configuration rules from DynamoDB')

    # build a list of any IDs (anywhere) that we should ignore
    ignore_ids = utils.build_ignore_list(configurations)

    # setup some lookup tables
    cache_data = utils.build_cache_maps(context, configurations, region, installed_region)
    all_instances = cache_data['instance_id_to_data']
    instance_configs = cache_data['instance_id_to_config']
    volume_snap_recent = cache_data['volume_id_to_most_recent_snapshot_date']

    for instance_id in set(all_instances.keys()):
        # before we go do some work
        if timeout_check(context, 'perform_snapshot'):
            break

        if instance_id in ignore_ids:
            continue

        snapshot_settings = instance_configs[instance_id]

        # parse out snapshot settings
        retention, frequency = utils.parse_snapshot_settings(snapshot_settings)

        # grab the data about this instance id, if we don't already have it
        instance_data = all_instances[instance_id]

        ami_id = instance_data['ImageId']
        LOG.info('Reviewing snapshots in region %s on instance %s', region, instance_id)

        for dev in instance_data.get('BlockDeviceMappings', []):
            # before we go make a bunch more API calls
            if timeout_check(context, 'perform_snapshot'):
                break

            # we probably should have been using volume keys from one of the
            # caches here, but since we're not, we're going to have to check here too
            LOG.debug('Considering device %s', dev)
            volume_id = dev['Ebs']['VolumeId']

            if volume_id in ignore_ids:
                continue

            # find snapshots
            recent = volume_snap_recent.get(volume_id)
            now = datetime.datetime.now(dateutil.tz.tzutc())

            # snapshot due?
            if should_perform_snapshot(frequency, now, volume_id, recent):
                LOG.debug('Performing snapshot for %s, calculating tags', volume_id)
            else:
                LOG.debug('NOT Performing snapshot for %s', volume_id)
                continue

            # perform actual snapshot and create tag: retention + now() as a Y-M-D
            delete_on_dt = now + retention
            delete_on = delete_on_dt.strftime('%Y-%m-%d')

            volume_data = utils.get_volume(volume_id, region=region)
            expected_tags = utils.calculate_relevant_tags(
                instance_data.get('Tags', None),
                volume_data.get('Tags', None))

            utils.snapshot_and_tag(
                instance_id,
                ami_id,
                volume_id,
                delete_on,
                region,
                additional_tags=expected_tags)


def should_perform_snapshot(frequency, now, volume_id, recent=None):
    """if newest snapshot time + frequency < now(), do a snapshot"""
    # if no recent snapshot, one is always due
    if recent is None:
        LOG.debug('Last snapshot for volume %s was not found', volume_id)
        LOG.debug('Next snapshot for volume %s should be due now', volume_id)
        return True
    else:
        LOG.debug('Last snapshot for volume %s was at %s', volume_id, recent)

    if utils.is_timedelta_expression(frequency):
        LOG.debug('Next snapshot for volume %s should be due at %s',
                  volume_id,
                  (recent + frequency))
        return (recent + frequency) < now

    if utils.is_crontab_expression(frequency):
        # at recent['StartTime'], when should we have run next?
        expected_next_seconds = frequency.next(recent, default_utc=True)
        expected_next = recent + timedelta(seconds=expected_next_seconds)

        LOG.debug("Crontab expr:")
        LOG.debug("\tnow(): %s", now)
        LOG.debug("\trecent['StartTime']: %s", recent)
        LOG.debug("\texpected_next_seconds: %s", expected_next_seconds)
        LOG.debug("\texpected_next: %s", expected_next)

        # if the next snapshot that should exist is before the current time
        return expected_next < now

    raise Exception('Could not determine if snapshot was due', frequency, recent)


def sanitize_serializable(instance_data):
    """Check every value is serializable, build new dict with safe values"""
    output = {}

    # we can't serialize all values, so just grab the ones we can
    for k, v in instance_data.iteritems():
        can_ser = can_serialize_json(k, v)
        if not can_ser:
            continue

        output[k] = v

    return output


def can_serialize_json(key, value):
    """Return true if it's safe to pass this to json.dumps()"""

    try:
        json.dumps({key: value})
        return True
    except:
        return False
