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
"""Module for testing replication module."""

import boto3
from moto import mock_ec2, mock_sns, mock_dynamodb2, mock_sts, mock_iam
from ebs_snapper import replication, dynamo, utils, mocks
from ebs_snapper import AWS_MOCK_ACCOUNT


def setup_module(module):
    import logging
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO)


@mock_ec2
@mock_dynamodb2
@mock_sns
@mock_iam
@mock_sts
def test_perform_fanout_all_regions_replication(mocker):
    """Test for method of the same name."""

    # make a dummy SNS topic
    mocks.create_sns_topic('ReplicationSnapshotTopic')
    expected_sns_topic = utils.get_topic_arn('ReplicationSnapshotTopic', 'us-east-1')

    dummy_regions = ['us-west-2', 'us-east-1']

    # make some dummy snapshots in two regions
    snapshot_map = {}
    for dummy_region in dummy_regions:
        client = boto3.client('ec2', region_name=dummy_region)
        volume = client.create_volume(Size=100, AvailabilityZone=dummy_region + "a")
        snapshot = client.create_snapshot(VolumeId=volume['VolumeId'])
        snapshot_map[snapshot['SnapshotId']] = dummy_region

    # patch the final message sender method
    ctx = utils.MockContext()
    mocker.patch('ebs_snapper.replication.send_fanout_message')
    replication.perform_fanout_all_regions(ctx)

    # fan out, and be sure we touched every instance we created before
    for r in dummy_regions:
        replication.send_fanout_message.assert_any_call(
            context=ctx,
            region=r,
            sns_topic=expected_sns_topic,
            cli=False)  # pylint: disable=E1103


@mock_ec2
@mock_dynamodb2
@mock_sns
@mock_iam
@mock_sts
def test_perform_replication(mocker):
    """Test for method of the same name."""

    # some default settings for this test
    region_a = 'us-west-1'
    region_b = 'us-east-1'
    ctx = utils.MockContext()

    # setup some dummy configuration for snapshots
    mocks.create_dynamodb('us-east-1')
    snapshot_settings = {'snapshot': {'minimum': 5, 'frequency': '2 hours', 'retention': '5 days'},
                         'match': {'tag:backup': 'yes'}}
    dynamo.store_configuration('us-east-1', 'some_unique_id', AWS_MOCK_ACCOUNT, snapshot_settings)

    # clients
    client_a = boto3.client('ec2', region_name=region_a)
    client_b = boto3.client('ec2', region_name=region_b)

    # create a volume in region_a
    volume = client_a.create_volume(Size=100, AvailabilityZone=region_a + "a")
    snapshot_name = "Snapshot_Name"
    snapshot_description = "Something from EBS Snapper"
    snapshot = client_a.create_snapshot(
        VolumeId=volume['VolumeId'],
        Description=snapshot_description
    )
    client_a.create_tags(
        Resources=[snapshot['SnapshotId']],
        Tags=[
            {'Key': 'replication_dst_region', 'Value': region_b},
            {'Key': 'Name', 'Value': snapshot_name},
        ]
    )

    # trigger replication, assert that we copied a snapshot to region_b
    mocker.patch('ebs_snapper.utils.copy_snapshot_and_tag')
    replication.perform_replication(ctx, region_a)
    utils.copy_snapshot_and_tag.assert_any_call(  # pylint: disable=E1103
        ctx,
        region_a,
        region_b,
        snapshot_name,
        snapshot['SnapshotId'],
        snapshot_description)

    # now create that snapshot manually
    replica_volume = client_b.create_volume(Size=100, AvailabilityZone=region_b + "a")
    replica_snapshot_description = "Something from EBS Snapper, copied to region b"
    replica_snapshot = client_b.create_snapshot(
        VolumeId=replica_volume['VolumeId'],
        Description=replica_snapshot_description
    )
    client_b.create_tags(
        Resources=[replica_snapshot['SnapshotId']],
        Tags=[
            {'Key': 'replication_src_region', 'Value': region_a},
            {'Key': 'replication_snapshot_id', 'Value': snapshot['SnapshotId']}
        ]
    )

    # trigger replication a second time, and confirm still one copy (not 2)
    utils.copy_snapshot_and_tag.reset_mock()
    replication.perform_replication(ctx, region_a)
    utils.copy_snapshot_and_tag.assert_not_called()  # pylint: disable=E1103

    # now delete the original and trigger replication, confirm replica deleted
    utils.delete_snapshot(snapshot['SnapshotId'], region_a)
    mocker.patch('ebs_snapper.utils.delete_snapshot')
    replication.perform_replication(ctx, region_b)
    utils.delete_snapshot.assert_any_call(  # pylint: disable=E1103
        replica_snapshot['SnapshotId'],
        region_b
    )
