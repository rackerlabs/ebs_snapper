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
"""Module for managing snapshot replication."""

from __future__ import print_function
from time import sleep
import json
import logging
import boto3
from ebs_snapper import timeout_check, dynamo, utils


LOG = logging.getLogger()


def perform_fanout_all_regions(context, cli=False):
    """For every region, send a message (lambda) or run replication (cli)"""

    sns_topic = utils.get_topic_arn('ReplicationSnapshotTopic')
    LOG.debug('perform_fanout_all_regions using SNS topic %s', sns_topic)

    # get regions with instances running or stopped
    regions = utils.get_regions(must_contain_snapshots=True)
    for region in regions:
        sleep(5)  # API rate limiting help

        send_fanout_message(
            context=context,
            region=region,
            sns_topic=sns_topic,
            cli=cli)


def send_fanout_message(context, region, sns_topic, cli=False):
    """Send message to perform replication in region."""

    message = json.dumps({'region': region})
    LOG.debug('send_fanout_message: %s', message)

    if cli:
        perform_replication(context, region)
    else:
        utils.sns_publish(TopicArn=sns_topic, Message=message)


def perform_replication(context, region, installed_region='us-east-1'):
    """Check the region and instance, and see if we should clean or create copies"""
    LOG.info('Performing snapshot replication in region %s', region)

    # TL;DR -- always try to clean up first, before making new copies.

    # build a list of ignore IDs, just in case they are relevant here
    configurations = dynamo.list_configurations(context, installed_region)
    ignore_ids = utils.build_ignore_list(configurations)
    LOG.debug('Fetched all configured ignored IDs rules from DynamoDB')

    # 1. collect snapshots from this region
    relevant_tags = ['replication_src_region', 'replication_dst_region']
    found_snapshots = utils.build_replication_cache(
        context,
        relevant_tags,
        configurations,
        region,
        installed_region
    )

    # 2. evaluate snapshots that were copied to this region, if source not found, delete
    for snapshot in found_snapshots.get('replication_src_region', []):
        snapshot_id = snapshot['SnapshotId']
        snapshot_description = snapshot['Description']

        if timeout_check(context, 'perform_replication'):
            break

        if snapshot_id in ignore_ids:
            continue

        if snapshot['State'] in ['pending', 'error']:
            LOG.warn('Skip cleaning up this snapshot ' + snapshot_id +
                     ' due to ' + snapshot['State'] + ' state: ' + snapshot_description)
            continue

        LOG.info('Working on cleaning up this snapshot ' + snapshot_id +
                 ' (if needed): ' + snapshot_description)

        # what region did this come from?
        tag_pairs = snapshot.get('Tags', [])
        region_tag_pair = [x for x in tag_pairs
                           if x.get('Key', None) == 'replication_src_region']
        region_tag_value = region_tag_pair[0].get('Value')

        # what snapshot id did this come from?
        snapshotid_tag_pair = [x for x in tag_pairs
                               if x.get('Key', None) == 'replication_snapshot_id']
        snapshotid_tag_value = snapshotid_tag_pair[0].get('Value')

        ec2_source = boto3.client('ec2', region_name=region_tag_value)
        try:
            found_originals = ec2_source.describe_snapshots(
                SnapshotIds=[snapshotid_tag_value],  # we think the original snapshot id is this
                Filters=[
                    # where it gets copied to should be us
                    {'Name': 'tag:replication_dst_region', 'Values': [region]},
                ]
            )
        except Exception as err:
            if 'InvalidSnapshot.NotFound' in str(err):
                found_originals = {'Snapshots': []}
            else:
                raise err

        num_found = len(found_originals.get('Snapshots', []))
        if num_found > 0:
            LOG.info('Not removing this snapshot ' + snapshot_id + ' from ' + region +
                     ' since snapshot_id ' + snapshotid_tag_value +
                     ' was already found in ' + region_tag_value)
            continue

        # ax it!
        LOG.warn('Removing this snapshot ' + snapshot_id + ' from ' + region +
                 ' since snapshot_id ' + snapshotid_tag_value +
                 ' was not found in ' + region_tag_value)
        utils.delete_snapshot(snapshot_id, region)

    # 3. evaluate snapshots that should be copied from this region, if dest not found, copy and tag
    for snapshot in found_snapshots.get('replication_dst_region', []):
        snapshot_id = snapshot['SnapshotId']
        snapshot_description = snapshot['Description']

        if timeout_check(context, 'perform_replication'):
            break

        if snapshot_id in ignore_ids:
            continue

        if snapshot['State'] in ['pending', 'error']:
            LOG.warn('Skip copying this snapshot ' + snapshot_id +
                     ' due to ' + snapshot['State'] + ' state: ' + snapshot_description)
            continue

        LOG.info('Working on copying this snapshot ' + snapshot_id +
                 ' (if needed): ' + snapshot_description)

        # what region should this be mapped to?
        tag_pairs = snapshot.get('Tags', [])
        region_tag_pair = [x for x in tag_pairs if x.get('Key', None) == 'replication_dst_region']
        region_tag_value = region_tag_pair[0].get('Value')

        # does it already exist in the target region?
        ec2_destination = boto3.client('ec2', region_name=region_tag_value)
        found_replicas = ec2_destination.describe_snapshots(
            Filters=[
                # came from our region originally
                {'Name': 'tag:replication_src_region', 'Values': [region]},

                # came from our snapshot originally
                {'Name': 'tag:replication_snapshot_id', 'Values': [snapshot_id]}
            ]
        )
        num_found = len(found_replicas.get('Snapshots', []))
        if num_found > 0:
            LOG.info('Not creating more snapshots, since snapshot_id ' + snapshot_id +
                     ' was already found in ' + region_tag_value)
            continue

        # we need to make one in the target region
        LOG.warn('Creating a new snapshot, since snapshot_id ' + snapshot_id +
                 ' was not already found in ' + region_tag_value)
        utils.copy_snapshot_and_tag(
            context,
            region,
            region_tag_value,
            snapshot_id,
            snapshot_description)
