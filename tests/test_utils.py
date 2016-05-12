# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing utils module."""

import boto3
from moto import mock_ec2, mock_sns
from ebs_snapper_lambda_v2 import utils


@mock_ec2
def test_get_owner_id():
    """Test for method of the same name."""
    # make some dummy instances
    client = boto3.client('ec2', region_name='us-west-2')
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # show that get_owner_id can get the dummy owner id
    assert ['111122223333'] == utils.get_owner_id()


@mock_ec2
def test_get_regions_with_instances():
    """Test for method of the same name."""
    client = boto3.client('ec2', region_name='us-west-2')

    # toss an instance in us-west-2
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # be sure we get us-west-2 *only*
    assert ['us-west-2'] == utils.get_regions(must_contain_instances=True)


@mock_ec2
def test_get_regions_ignore_instances():
    """Test for method of the same name."""
    found_instances = utils.get_regions(must_contain_instances=False)
    expected_regions = ['eu-west-1', 'sa-east-1', 'us-east-1',
                        'ap-northeast-1', 'us-west-2', 'us-west-1']
    for expected_region in expected_regions:
        assert expected_region in found_instances


@mock_ec2
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
def test_apply_instances():
    """Test for method of the same name."""
    client = boto3.client('ec2', region_name='us-west-2')
    client.run_instances(ImageId='ami-123abc', MinCount=5, MaxCount=5)

    found_instances = []
    utils.apply_instances('us-west-2', found_instances.append)

    # ensure .append was called for every instance
    assert len(found_instances) == 5


@mock_ec2
@mock_sns
def test_get_topic_arn():
    """Test for method of the same name."""
    topic_name = 'please-dont-exist'

    # make an SNS topic
    client = boto3.client('sns', region_name='us-west-2')
    response = client.create_topic(Name=topic_name)
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200

    # see if our code can find it!
    found_arn = utils.get_topic_arn(topic_name)
    assert 'us-west-2' in found_arn
    assert topic_name in found_arn
