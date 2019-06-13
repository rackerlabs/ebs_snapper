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
import sys
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
    snap_cached_src_regions = []
    snap_cached_dst_regions = []
    src_snap_list = []
    replication_snap_list = []
    relevant_tags = ['replication_src_region', 'replication_dst_region']
    found_snapshots = utils.build_replication_cache(
        context,
        relevant_tags,
        configurations,
        region,
        installed_region
    )
    # 1a. build snapshot cache from all source regions
    #snap_cached_src_regions.append(region)
    for snapshot_regions in found_snapshots.get('replication_src_region', []):
        # what region did this come from?
        tag_pairs = snapshot_regions.get('Tags', [])
        region_tag_pair = [x for x in tag_pairs
                           if x.get('Key', None) == 'replication_src_region']
        region_tag_value = region_tag_pair[0].get('Value')
        if (region_tag_value not in snap_cached_src_regions):
            LOG.info('Caching snapshots in source region: ' + region_tag_value)
            snap_cached_src_regions.append(region_tag_value)

            ec2_source = boto3.client('ec2', region_name=region_tag_value)
            try:
                response = ec2_source.describe_snapshots(
                    Filters=[
                    {'Name': 'tag:replication_dst_region', 'Values': [region]},
                    ]
                )
	        mysnaps = response['Snapshots']
            except Exception as err:
                if 'InvalidSnapshot.NotFound' in str(err):
		    mysnaps = {'Snapshots', []}
		else:
		    raise err
			
            for snap in mysnaps:
                src_snap_list.append(snap['SnapshotId'])

            LOG.info('Caching completed for source region: ' + region_tag_value + ': cache size: ' + str(len(src_snap_list)))
            sleep(1)

    # 1b. build snapshot cache for all destination regions
    for snapshot_regions in found_snapshots.get('replication_dst_region', []):
        # which region is destination
        tag_pairs = snapshot_regions.get('Tags', [])
        region_tag_pair = [x for x in tag_pairs
                           if x.get('Key', None) == 'replication_dst_region']
        region_tag_value = region_tag_pair[0].get('Value')
        if (region_tag_value not in snap_cached_dst_regions):
            LOG.info('Caching snapshots in destination region: ' + region_tag_value)
            snap_cached_dst_regions.append(region_tag_value)

            ec2_source = boto3.client('ec2', region_name=region_tag_value)
            try:
                response = ec2_source.describe_snapshots(
                    Filters=[
                    {'Name': 'tag:replication_src_region', 'Values': [region]},
                    ]
                )
                mysnaps = response['Snapshots']
            except Exception as err:
                if 'InvalidSnapshot.NotFound' in str(err):
                    mysnaps = {'Snapshots', []}
                else:
                    raise err

            for snap in mysnaps:
                for tags in snap['Tags']:
                    if tags["Key"] == 'replication_snapshot_id':
                        replication_snap_list.append(tags["Value"])

            LOG.info('Caching completed for destination region: ' + region_tag_value + ': cache size: ' + str(len(replication_snap_list)))
            sleep(1)

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

        if snapshotid_tag_value in src_snap_list:
            LOG.info('Not removing this snapshot ' + snapshot_id + ' from ' + region +
                     ' since snapshot_id ' + snapshotid_tag_value +
                     ' was found in ' + region_tag_value)
            continue

        # ax it!
        LOG.warn('Removing this snapshot ' + snapshot_id + ' from ' + region +
                 ' since snapshot_id ' + snapshotid_tag_value +
                 ' was not found in ' + region_tag_value)
        utils.delete_snapshot(snapshot_id, region)
        sleep(2)

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

	name_tag_pair = [x for x in tag_pairs if x.get('Key', None) == 'Name']
	name_tag_value = name_tag_pair[0].get('Value')

        # does it already exist in the target region?
        if snapshot_id in replication_snap_list:
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
            name_tag_value,
            snapshot_id,
            snapshot_description)
