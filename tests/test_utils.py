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
from ebs_snapper import AWS_MOCK_ACCOUNT


def setup_module(module):
    import logging
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO)


@mock_ec2
@mock_iam
@mock_sts
def test_get_owner_id():
    """Test for method of the same name."""
    # make some dummy instances
    client = boto3.client('ec2', region_name='us-west-2')
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # show that get_owner_id can get the dummy owner id
    assert [AWS_MOCK_ACCOUNT] == utils.get_owner_id(utils.MockContext())


@mock_ec2
@mock_iam
@mock_sts
def test_get_regions_with_instances_or_snapshots():
    """Test for method of the same name."""
    client_uswest2 = boto3.client('ec2', region_name='us-west-2')

    # toss an instance in us-west-2
    client_uswest2.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # be sure we get us-west-2 *only*
    assert ['us-west-2'] == utils.get_regions(
        must_contain_instances=True,
        must_contain_snapshots=False)

    # now say we don't filter by instances, be sure we get a lot of regions
    found_regions = utils.get_regions(
        must_contain_instances=False,
        must_contain_snapshots=False)
    expected_regions = ['eu-west-1', 'sa-east-1', 'us-east-1',
                        'ap-northeast-1', 'us-west-2', 'us-west-1']
    for expected_region in expected_regions:
        assert expected_region in found_regions

    # now take a snapshot
    client_uswest1 = boto3.client('ec2', region_name='us-west-1')
    volume_results = client_uswest1.create_volume(Size=100, AvailabilityZone='us-west-1a')
    client_uswest1.create_snapshot(VolumeId=volume_results['VolumeId'])

    # be sure that snapshot filter works and only returns the snapshot region
    assert ['us-west-1'] == utils.get_regions(
        must_contain_instances=False,
        must_contain_snapshots=True)

    # now filter by both, should be nothing returned
    found_regions = utils.get_regions(must_contain_instances=True, must_contain_snapshots=True)
    assert len(found_regions) == 0

    # now snap in us-west-2 where we have an instance as well
    volume_results2 = client_uswest2.create_volume(Size=100, AvailabilityZone='us-west-2a')
    client_uswest2.create_snapshot(VolumeId=volume_results2['VolumeId'])
    found_regions = utils.get_regions(must_contain_instances=True, must_contain_snapshots=True)
    assert found_regions == ['us-west-2']


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
@mock_iam
@mock_sts
def test_region_contains_snapshots():
    """Test for method of the same name."""
    client = boto3.client('ec2', region_name='us-west-2')

    # toss a volume in us-west-2 and snapshot it
    volume_results = client.create_volume(Size=100, AvailabilityZone='us-west-1a')
    client.create_snapshot(VolumeId=volume_results['VolumeId'])

    # be sure we get us-west-2
    assert utils.region_contains_snapshots('us-west-2')

    # be sure we don't get us-east-1
    assert not utils.region_contains_snapshots('us-east-1')


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
        volume_tags.append({'Key': "foo-" + str(i), 'Value': "bar-" + str(i + 100)})

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

    for k, v in expected_pairs.iteritems():
        assert {'Key': k, 'Value': v} in created_snap['Tags']


@mock_ec2
@mock_sns
@mock_iam
@mock_sts
def test_build_replication_cache():
    """Test that we build a list of snapshots with correct groupings"""

    # setup variables
    region = 'us-west-2'
    installed_region = 'us-east-1'
    context = utils.MockContext()
    tags = ['replication_src_region', 'replication_dst_region']
    configurations = []
    client = boto3.client('ec2', region_name=region)

    # toss a volume in us-west-2 and snapshot it twice
    volume_results = client.create_volume(Size=100, AvailabilityZone='us-west-1a')
    src_snapshot = client.create_snapshot(VolumeId=volume_results['VolumeId'])
    dst_snapshot = client.create_snapshot(VolumeId=volume_results['VolumeId'])

    # build the cache and be sure they don't show up
    cache1 = utils.build_replication_cache(context, tags, configurations, region, installed_region)
    for t in tags:
        assert len(cache1.get(t, [])) == 0

    # now tag...
    client.create_tags(
        Resources=[src_snapshot['SnapshotId']],
        Tags=[{'Key': 'replication_src_region', 'Value': 'us-west-1'}]
    )
    client.create_tags(
        Resources=[dst_snapshot['SnapshotId']],
        Tags=[{'Key': 'replication_dst_region', 'Value': 'us-west-1'}]
    )

    # build cache again, and expect to see the tagged snapshots
    cache2 = utils.build_replication_cache(context, tags, configurations, region, installed_region)
    assert cache2['replication_src_region'][0]['SnapshotId'] == src_snapshot['SnapshotId']
    assert cache2['replication_dst_region'][0]['SnapshotId'] == dst_snapshot['SnapshotId']
