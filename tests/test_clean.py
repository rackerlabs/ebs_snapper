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
"""Module for testing clean module."""

import json
import datetime
from moto import mock_ec2, mock_sns, mock_dynamodb2, mock_iam, mock_sts
from ebs_snapper import clean, utils, mocks, dynamo
import dateutil


@mock_ec2
@mock_sns
@mock_dynamodb2
@mock_iam
@mock_sts
def test_perform_fanout_all_regions_clean(mocker):
    """Test for method of the same name."""
    mocks.create_sns_topic('CleanSnapshotTopic')
    mocks.create_dynamodb()

    expected_regions = utils.get_regions()
    for r in expected_regions:  # must have an instance in the region to clean it
        mocks.create_instances(region=r)
    expected_sns_topic = utils.get_topic_arn('CleanSnapshotTopic', 'us-east-1')

    ctx = utils.MockContext()
    mocker.patch('ebs_snapper.clean.send_fanout_message')

    # fan out, and be sure we touched every region
    clean.perform_fanout_all_regions(ctx)
    for r in expected_regions:
        clean.send_fanout_message.assert_any_call(  # pylint: disable=E1103
            ctx,
            cli=False,
            region=r,
            topic_arn=expected_sns_topic)


@mock_ec2
@mock_sns
@mock_iam
@mock_sts
def test_send_fanout_message_clean(mocker):
    """Test for method of the same name."""

    mocks.create_sns_topic('testing-topic')
    expected_sns_topic = utils.get_topic_arn('testing-topic', 'us-east-1')
    ctx = utils.MockContext()

    mocker.patch('ebs_snapper.utils.sns_publish')
    clean.send_fanout_message(ctx, region='us-west-2', topic_arn=expected_sns_topic)
    utils.sns_publish.assert_any_call(  # pylint: disable=E1103
        TopicArn=expected_sns_topic,
        Message=json.dumps({'region': 'us-west-2'}))


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_clean_tagged_snapshots(mocker):
    """Test for method of the same name."""
    # default settings
    region = 'us-east-1'
    mocks.create_dynamodb(region)

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]
    ctx = utils.MockContext()

    # setup the min # snaps for the instance
    config_data = {
        "match": {"instance-id": instance_id},
        "snapshot": {
            "retention": "6 days", "minimum": 0, "frequency": "13 hours"
        }
    }

    # put it in the table, be sure it succeeded
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']

    # make a snapshot that should be deleted today too
    now = datetime.datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')
    utils.snapshot_and_tag(instance_id, 'ami-123abc', volume_id, delete_on, region)
    snapshot_id = utils.most_recent_snapshot(volume_id, region)['SnapshotId']

    mocker.patch('ebs_snapper.utils.delete_snapshot')
    clean.clean_snapshot(ctx, region)

    # ensure we deleted this snapshot if it was ready to die today
    utils.delete_snapshot.assert_any_call(snapshot_id, region)  # pylint: disable=E1103

    # now raise the minimum, and check to be sure we didn't delete
    utils.delete_snapshot.reset_mock()  # pylint: disable=E1103
    config_data['snapshot']['minimum'] = 5
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)
    clean.clean_snapshot(ctx, region)
    utils.delete_snapshot.assert_not_called()  # pylint: disable=E1103


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_clean_snapshots_tagged_timeout(mocker):
    """Test that we _DONT_ clean anything if runtime > 4 minutes"""
    # default settings
    region = 'us-east-1'
    mocks.create_dynamodb(region)
    ctx = utils.MockContext()
    ctx.set_remaining_time_in_millis(5)  # 5 millis remaining

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]

    # setup the min # snaps for the instance
    config_data = {
        "match": {"instance-id": instance_id},
        "snapshot": {
            "retention": "6 days", "minimum": 0, "frequency": "13 hours"
        }
    }

    # put it in the table, be sure it succeeded
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']

    # make a snapshot that should be deleted today too
    now = datetime.datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')
    utils.snapshot_and_tag(instance_id, 'ami-123abc', volume_id, delete_on, region)

    mocker.patch('ebs_snapper.utils.delete_snapshot')
    clean.clean_snapshot(ctx, region)

    # ensure we DO NOT take a snapshot if our runtime was 5 minutes
    assert not utils.delete_snapshot.called


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_clean_tagged_snapshots_ignore_instance(mocker):
    """Test for method of the same name."""
    # default settings
    region = 'us-east-1'
    mocks.create_dynamodb(region)

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]
    ctx = utils.MockContext()

    # setup the min # snaps for the instance
    config_data = {
        "match": {"instance-id": instance_id},
        "snapshot": {
            "retention": "6 days", "minimum": 0, "frequency": "13 hours"
        },
        "ignore": [instance_id]
    }

    # put it in the table, be sure it succeeded
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']

    # make a snapshot that should be deleted today too
    now = datetime.datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')
    utils.snapshot_and_tag(instance_id, 'ami-123abc', volume_id, delete_on, region)
    utils.most_recent_snapshot(volume_id, region)['SnapshotId']

    mocker.patch('ebs_snapper.utils.delete_snapshot')
    clean.clean_snapshot(ctx, region)

    # ensure we ignored the instance from this volume
    utils.delete_snapshot.assert_not_called()  # pylint: disable=E1103


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_clean_tagged_snapshots_ignore_volume(mocker):
    """Test for method of the same name."""
    # default settings
    region = 'us-east-1'
    mocks.create_dynamodb(region)

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]
    ctx = utils.MockContext()

    # setup the min # snaps for the instance
    config_data = {
        "match": {"instance-id": instance_id},
        "snapshot": {
            "retention": "6 days", "minimum": 0, "frequency": "13 hours"
        },
        "ignore": []
    }

    # put it in the table, be sure it succeeded
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']
    config_data["ignore"].append(volume_id)

    # make a snapshot that should be deleted today too
    now = datetime.datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')
    utils.snapshot_and_tag(instance_id, 'ami-123abc', volume_id, delete_on, region)
    snapshot_id = utils.most_recent_snapshot(volume_id, region)['SnapshotId']

    mocker.patch('ebs_snapper.utils.delete_snapshot')
    clean.clean_snapshot(ctx, region)

    # ensure we deleted this snapshot if it was ready to die today
    utils.delete_snapshot.assert_any_call(snapshot_id, region)  # pylint: disable=E1103

    # now raise the minimum, and check to be sure we didn't delete
    utils.delete_snapshot.reset_mock()  # pylint: disable=E1103
    config_data['snapshot']['minimum'] = 5
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)
    clean.clean_snapshot(ctx, region)
    utils.delete_snapshot.assert_not_called()  # pylint: disable=E1103
