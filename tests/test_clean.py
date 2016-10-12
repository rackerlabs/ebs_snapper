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
from datetime import timedelta
from moto import mock_ec2, mock_sns, mock_dynamodb2, mock_iam, mock_sts
from ebs_snapper import snapshot, clean, utils, mocks, dynamo
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

    mocker.patch('ebs_snapper.clean.send_fanout_message')

    # fan out, and be sure we touched every region
    clean.perform_fanout_all_regions()

    for r in expected_regions:
        clean.send_fanout_message.assert_any_call(  # pylint: disable=E1103
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

    mocker.patch('ebs_snapper.utils.sns_publish')
    clean.send_fanout_message(region='us-west-2', topic_arn=expected_sns_topic)
    utils.sns_publish.assert_any_call(  # pylint: disable=E1103
        TopicArn=expected_sns_topic,
        Message=json.dumps({'region': 'us-west-2'}))


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_clean_snapshot(mocker):
    """Test for method of the same name."""
    # def clean_snapshot(region):
    region = 'us-east-1'

    # need an instance to get figure out an owner
    instance_id = mocks.create_instances(region, count=1)[0]
    owner_ids = utils.get_owner_id()

    # setup the min # snaps for the instance
    config_data = {
        "match": {"instance-id": instance_id},
        "snapshot": {
            "retention": "-7 days", "minimum": 0, "frequency": "13 hours"
        }
    }

    # put it in the table, be sure it succeeded
    mocks.create_dynamodb(region)
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)

    # make a snapshot, so we can find it and delete it
    snapshot.perform_snapshot(region, instance_id, config_data)

    # mock the over-arching method that just loops over the last 10 days
    now = datetime.datetime.now(dateutil.tz.tzutc())
    mocker.patch('ebs_snapper.clean.clean_snapshots_tagged')
    clean.clean_snapshot(region, started_run=now)

    # be sure we call delete for the negative retention in -7 days
    delete_on = datetime.date.today() + timedelta(days=-7)
    clean.clean_snapshots_tagged.assert_any_call(  # pylint: disable=E1103
        now,
        delete_on.strftime('%Y-%m-%d'),
        owner_ids,
        region,
        [config_data])


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
    owner_ids = utils.get_owner_id()

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

    now_time = datetime.datetime.now(dateutil.tz.tzutc())

    mocker.patch('ebs_snapper.utils.delete_snapshot')
    clean.clean_snapshots_tagged(now_time,
                                 now.strftime('%Y-%m-%d'),
                                 owner_ids, region, [config_data])

    # ensure we deleted this snapshot if it was ready to die today
    utils.delete_snapshot.assert_any_call(snapshot_id, region)  # pylint: disable=E1103

    # now raise the minimum, and check to be sure we didn't delete
    utils.delete_snapshot.reset_mock()  # pylint: disable=E1103
    config_data['snapshot']['minimum'] = 5
    dynamo.store_configuration(region, 'foo', '111122223333', config_data)
    clean.clean_snapshots_tagged(now_time, now.strftime('%Y-%m-%d'),
                                 owner_ids, region, [config_data])
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

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]
    owner_ids = utils.get_owner_id()

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

    now_time = datetime.datetime.now(dateutil.tz.tzutc()) + timedelta(minutes=-5)

    mocker.patch('ebs_snapper.utils.delete_snapshot')
    clean.clean_snapshots_tagged(now_time,
                                 now.strftime('%Y-%m-%d'),
                                 owner_ids, region, [config_data])

    # ensure we DO NOT take a snapshot if our runtime was 5 minutes
    assert not utils.delete_snapshot.called
