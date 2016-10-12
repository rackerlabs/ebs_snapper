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
"""Module for testing utils module."""

from datetime import datetime, timedelta
import dateutil
import boto3
from moto import mock_ec2, mock_sns, mock_iam, mock_sts
from ebs_snapper import utils, mocks


@mock_ec2
@mock_iam
@mock_sts
def test_get_owner_id():
    """Test for method of the same name."""
    # make some dummy instances
    client = boto3.client('ec2', region_name='us-west-2')
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # show that get_owner_id can get the dummy owner id
    assert ['111122223333'] == utils.get_owner_id()


@mock_ec2
@mock_iam
@mock_sts
def test_get_regions_with_instances():
    """Test for method of the same name."""
    client = boto3.client('ec2', region_name='us-west-2')

    # toss an instance in us-west-2
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # be sure we get us-west-2 *only*
    assert ['us-west-2'] == utils.get_regions(must_contain_instances=True)


@mock_ec2
@mock_iam
@mock_sts
def test_get_regions_ignore_instances():
    """Test for method of the same name."""
    found_instances = utils.get_regions(must_contain_instances=False)
    expected_regions = ['eu-west-1', 'sa-east-1', 'us-east-1',
                        'ap-northeast-1', 'us-west-2', 'us-west-1']
    for expected_region in expected_regions:
        assert expected_region in found_instances


@mock_ec2
@mock_iam
@mock_sts
def test_region_contains_instances():
    """Test for method of the same name."""
    client = boto3.client('ec2', region_name='us-west-2')

    # toss an instance in us-west-2
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # be sure we get us-west-2
    assert utils.region_contains_instances('us-west-2')

    # be sure we don't get us-east-1
    assert not utils.region_contains_instances('us-east-1')


@mock_ec2
@mock_sns
@mock_iam
@mock_sts
def test_get_topic_arn():
    """Test for method of the same name."""
    topic_name = 'please-dont-exist'

    # make an SNS topic
    mocks.create_sns_topic(topic_name, region_name='us-west-2')

    # see if our code can find it!
    found_arn = utils.get_topic_arn(topic_name, default_region='us-west-2')
    assert 'us-west-2' in found_arn
    assert topic_name in found_arn


def test_convert_configurations_to_boto_filter():
    """Test for method of the same name"""

    test_input = {
        "instance-id": "i-abc12345",
        "tag:key": "tag-value",
        "tag:Name": "legacy_server_name_*"
    }

    test_output = [
        {
            'Name': 'instance-id',
            'Values': ['i-abc12345']
        },
        {
            'Name': 'tag:key',
            'Values': ['tag-value']
        },
        {
            'Name': 'tag:Name',
            'Values': ['legacy_server_name_*']
        }
    ]

    real_output = utils.convert_configurations_to_boto_filter(test_input)
    assert sorted(real_output) == sorted(test_output)


def test_flatten():
    """Ensure flatten method can really flatten an array"""
    input_arr = [1, 2, [3, 4], [5, 6, 7]]
    output_arr = utils.flatten(input_arr)

    assert output_arr == range(1, 8)


def test_parse_snapshot_setting_timedelta():
    """Test for method of the same name"""
    snapshot_settings = {
        'snapshot': {'minimum': 5, 'frequency': '2 hours', 'retention': '5 days'},
        'match': {'tag:backup': 'yes'}
    }
    retention, frequency = utils.parse_snapshot_settings(snapshot_settings)

    assert retention == timedelta(5)  # 5 days
    assert frequency == timedelta(0, 7200)  # 2 hours


def test_parse_snapshot_setting_crontab():
    """Test for method of the same name"""
    snapshot_settings = {
        'snapshot': {'minimum': 5, 'frequency': '30 * * * *', 'retention': '5 days'},
        'match': {'tag:backup': 'yes'}
    }
    retention, frequency = utils.parse_snapshot_settings(snapshot_settings)
    assert retention == timedelta(5)  # 5 days

    # generate some dates and times that we'll use to check crontab
    eleven_twentyfive = datetime(2011, 7, 17, 11, 25)
    eleven_thirtyfive = datetime(2011, 7, 17, 11, 35)

    offset_soon = frequency.next(eleven_twentyfive, default_utc=True)

    # 5 minutes from eleven_twentyfive
    assert timedelta(seconds=offset_soon) == timedelta(seconds=300)

    offset_later = frequency.next(eleven_thirtyfive, default_utc=True)
    # 5 minutes from eleven_thirtyfive
    assert timedelta(seconds=offset_later) == timedelta(seconds=3300)


@mock_ec2
def test_get_instance():
    """Test for method of the same name"""
    # def get_instance(instance_id, region):
    region = 'us-west-2'

    instance_id = mocks.create_instances(region, count=1)[0]
    found_instance = utils.get_instance(instance_id, region)
    assert found_instance['InstanceId'] == instance_id


@mock_ec2
@mock_iam
@mock_sts
def test_snapshot_helper_methods():
    """Test for the snapshot helper methods"""
    # def count_snapshots(volume_id, region):
    region = 'us-west-2'

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']

    # make some snapshots that should be deleted today too
    now = datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')

    # verify no snapshots, then we take one, then verify there is one
    assert utils.most_recent_snapshot(volume_id, region) is None
    utils.snapshot_and_tag(instance_id, 'ami-123abc', volume_id, delete_on, region)
    assert utils.most_recent_snapshot(volume_id, region) is not None

    # make 5 more
    for i in range(0, 5):  # pylint: disable=unused-variable
        utils.snapshot_and_tag(instance_id, 'ami-123abc', volume_id, delete_on, region)

    # check the count is 6
    assert utils.count_snapshots(volume_id, region) == 6

    # check that if we pull them all, there's 6 there too
    assert len(utils.get_snapshots_by_volume(volume_id, region)) == 6


@mock_ec2
@mock_iam
@mock_sts
def test_calculate_relevant_tags():
    """Confirm that tags are calculated correctly, and don't exceed 10"""
    # client.create_tags()
    region = 'us-west-2'
    client = boto3.client('ec2', region_name=region)

    # some instance tags (pad to fill it after)
    instance_tags = [
        {'Key': 'Foo', 'Value': 'Bar'},  # normal tag
        {'Key': 'BusinessUnit', 'Value': 'Dept1'}  # billing tag
        ]
    for i in xrange(0, 8):
        instance_tags.append({'Key': "foo-" + str(i), 'Value': "bar-" + str(i)})

    # some volume tags (pad to fill it after)
    volume_tags = [
        {'Key': 'Foo', 'Value': 'Baz'},  # more normal tags
        {'Key': 'BusinessUnit', 'Value': 'Dept2'},  # billing tag override
        {'Key': 'Cluster', 'Value': 'Bank'}  # billing tag that won't override
        ]
    for i in xrange(0, 6):
        volume_tags.append({'Key': "foo-" + str(i), 'Value': "bar-" + str(i+100)})

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]
    client.create_tags(
        Resources=[instance_id],
        Tags=instance_tags
    )

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']
    client.create_tags(
        Resources=[volume_id],
        Tags=volume_tags
    )

    # make some snapshots that should be deleted today
    now = datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')

    instance_data = utils.get_instance(instance_id, region=region)
    volume_data = utils.get_volume(volume_id, region=region)
    expected_tags = utils.calculate_relevant_tags(
        instance_data.get('Tags', None),
        volume_data.get('Tags', None))

    # create the snapshot
    utils.snapshot_and_tag(instance_id,
                           'ami-123abc',
                           volume_id,
                           delete_on,
                           region,
                           additional_tags=expected_tags)

    # now confirm the tags are correct
    snapshots = utils.get_snapshots_by_volume(volume_id, region)
    created_snap = snapshots[0]

    # check those expected tags
    expected_pairs = {
        'BusinessUnit': 'Dept2',
        'Cluster': 'Bank',
        'DeleteOn': delete_on,
        # moto returns tags in very random order, for testing purposes,
        # so I can't really test anything else with the foo-* tags here
    }
    print(created_snap['Tags'])

    for k, v in expected_pairs.iteritems():
        assert {'Key': k, 'Value': v} in created_snap['Tags']


@mock_ec2
@mock_iam
@mock_sts
def test_find_deleteon_tags():
    """test def find_deleteon_tags(region_name, cutoff_date, max_tags=10)"""

    # client.create_tags()
    region = 'us-west-2'

    # make today's date
    now = datetime.now(dateutil.tz.tzutc())

    # create an instance and record the id
    i = 0
    created_instances = mocks.create_instances(region, count=15)

    for instance_id in created_instances:
        # some instance tags (pad to fill it after)
        cutoff = now - timedelta(days=-i)
        delete_on = cutoff.strftime('%Y-%m-%d')

        # create the snapshot
        volume_id = utils.get_volumes([instance_id], region)[0]['VolumeId']
        vol_data = utils.get_volume(volume_id, region=region)
        inst_data = utils.get_instance(instance_id, region=region)

        expected_tags = utils.calculate_relevant_tags(
            inst_data.get('Tags'),
            vol_data.get('Tags')
        )
        utils.snapshot_and_tag(instance_id,
                               'ami-123abc',
                               volume_id,
                               delete_on,
                               region,
                               additional_tags=expected_tags)

        found_tags = utils.find_deleteon_tags(region_name=region,
                                              cutoff_date=cutoff.date(), max_tags=20)

        # for instance_id in created_instances:
        assert len(found_tags) > 0
        assert str(now.strftime('%Y-%m-%d')) in found_tags

        i += 1
