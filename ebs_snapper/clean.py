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
"""Module for cleaning up snapshots."""

from __future__ import print_function
import datetime
import time
from datetime import timedelta
import json
import logging
import boto3
from ebs_snapper import utils, dynamo

LOG = logging.getLogger(__name__)


def perform_fanout_all_regions():
    """For every region, run the supplied function"""
    # get regions, regardless of instances
    sns_topic = utils.get_topic_arn('CleanSnapshotTopic')
    LOG.info('perform_fanout_all_regions using SNS topic %s', sns_topic)

    regions = utils.get_regions(must_contain_instances=True)
    for region in regions:
        send_fanout_message(region=region, topic_arn=sns_topic)


def send_fanout_message(region, topic_arn):
    """Publish an SNS message to topic_arn that specifies a region to review snapshots on"""
    message = json.dumps({'region': region})
    LOG.info('send_fanout_message: %s', message)

    utils.sns_publish(TopicArn=topic_arn, Message=message)


def clean_snapshot(region, installed_region='us-east-1'):
    """Check the region see if we should clean up any snapshots"""
    LOG.info('clean_snapshot in region %s', region)

    owner_ids = utils.get_owner_id(region)
    LOG.info('Filtering snapshots to clean by owner id %s', owner_ids)

    LOG.info('Fetching all possible configuration rules from DynamoDB')
    configurations = dynamo.list_configurations(installed_region)

    deleted_count = 0
    delete_on_date = datetime.date.today()
    deleted_count += clean_snapshots_tagged(
        delete_on_date,
        owner_ids,
        region,
        configurations)

    if deleted_count <= 0:
        LOG.warn('No snapshots were cleaned up for the entire region %s', region)


def clean_snapshots_tagged(delete_on_date, owner_ids, region, configurations, default_min_snaps=5):
    """Enable a start time reference."""
    start = time.time()
    """Remove snapshots where DeleteOn tag is delete_on datetime object"""
    ec2 = boto3.client('ec2', region_name=region)
    tagfilters = [
        {'Name': 'resource-type', 'Values': ['snapshot']},
        {'Name': 'key', 'Values': ['DeleteOn']},
    ]
    LOG.info("ec2.describe_tags with filters %s", tagfilters)
    ec2tags_response = ec2.describe_tags(Filters=tagfilters)
    LOG.info("ec2.describe_snapshots fin")
    if 'Tags' not in ec2tags_response or len(ec2tags_response['Tags']) <=0:
        LOG.debug('No Snapshots containing a DeleteOn Tag were discovered.')
    
    tagset = set()
    for tag in ec2tags_response['Tags']:
        if datetime.strptime(tag['Value'],"%Y-%m-%d") <= delete_on_date:
            tagset.add(tag['Value'])
    taglist = list(tagset)
    
    snapfilters = [
        {'Name': 'tag-key', 'Values': ['DeleteOn']},
        {'Name': 'tag-value', 'Values': [taglist]},
    ]
    LOG.info("ec2.describe_snapshots with filters %s", snapfilters)
    snapshot_response = ec2.describe_snapshots(OwnerIds=owner_ids, Filters=snapfilters)
    LOG.info("ec2.describe_snapshots fin")

    deleted_count = 0
    if 'Snapshots' not in snapshot_response or len(snapshot_response['Snapshots']) <= 0:
        LOG.debug('No snapshots were found using owners=%s, filters=%s',
                  owner_ids,
                  snapfilters)
        return deleted_count

    for snap in snapshot_response['Snapshots']:
        # attempt to identify the instance this applies to, so we can check minimums
        while (time.time() - start) < 240:
            try:
                snapshot_volume = snap['VolumeId']
                volume_instance = utils.get_instance_by_volume(snapshot_volume, region)

                # minimum required
                if volume_instance is None:
                    minimum_snaps = default_min_snaps
                else:
                    snapshot_settings = utils.get_snapshot_settings_by_instance(
                        volume_instance, configurations, region)
                    minimum_snaps = snapshot_settings['snapshot']['minimum']

                # current number of snapshots
                no_snaps = utils.count_snapshots(snapshot_volume, region)

                # if we have less than the minimum, don't delete this one
                if no_snaps < minimum_snaps:
                    LOG.warn('Not deleting snapshot %s from %s', snap['SnapshotId'], region)
                    LOG.warn('Only %s snapshots exist, below minimum of %s', no_snaps, minimum_snaps)
                    continue

            except:
                # if we couldn't figure out a minimum of snapshots,
                # don't clean this up -- these could be orphaned snapshots
                LOG.warn('Not deleting snapshot %s from %s, error encountered',
                         snap['SnapshotId'], region)
                continue

        LOG.warn('Deleting snapshot %s from %s', snap['SnapshotId'], region)
        utils.delete_snapshot(snap['SnapshotId'], region)
        deleted_count += 1

    return deleted_count
