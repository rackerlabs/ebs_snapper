# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing snapshot module."""

import boto3
from moto import mock_ec2, mock_sns, mock_dynamodb2
from ebs_snapper_lambda_v2 import snapshot, dynamo, utils
from ebs_snapper_lambda_v2 import mocks


@mock_ec2
@mock_dynamodb2
@mock_sns
def test_perform_fanout_all_regions_snapshot(mocker):
    """Test for method of the same name."""

    # make a dummy SNS topic
    mocks.create_sns_topic('CreateSnapshotTopic')

    dummy_regions = ['us-west-2', 'us-east-1']

    # make some dummy instances in two regions
    instance_maps = {}
    for dummy_region in dummy_regions:
        client = boto3.client('ec2', region_name=dummy_region)
        create_results = client.run_instances(ImageId='ami-123abc', MinCount=5, MaxCount=5)
        for instance_data in create_results['Instances']:
            instance_maps[instance_data['InstanceId']] = dummy_region

    # need to filter instances, so need dynamodb present
    mocks.create_dynamodb()
    config_data = {
        "match": {
            "instance-id": instance_maps.keys()
        },
        "snapshot": {
            "retention": "3 days",
            "minimum": 4,
            "frequency": "11 hours"
        }
    }
    dynamo.store_configuration('some_unique_id', '111122223333', config_data)

    # patch the final message sender method
    mocker.patch('ebs_snapper_lambda_v2.snapshot.perform_fanout_by_region')
    snapshot.perform_fanout_all_regions()

    # fan out, and be sure we touched every instance we created before
    for r in dummy_regions:
        snapshot.perform_fanout_by_region.assert_any_call(region=r)  # pylint: disable=E1103


@mock_ec2
@mock_dynamodb2
@mock_sns
def test_perform_fanout_by_region_snapshot(mocker):
    """Test for method of the same name."""

    # make a dummy SNS topic
    mocks.create_sns_topic('CreateSnapshotTopic')
    expected_sns_topic = utils.get_topic_arn('CreateSnapshotTopic')

    dummy_regions = ['us-west-2', 'us-east-1']

    # make some dummy instances in two regions
    instance_maps = {}
    for dummy_region in dummy_regions:
        client = boto3.client('ec2', region_name=dummy_region)
        create_results = client.run_instances(ImageId='ami-123abc', MinCount=5, MaxCount=5)
        for instance_data in create_results['Instances']:
            instance_maps[instance_data['InstanceId']] = dummy_region

    # need to filter instances, so need dynamodb present
    mocks.create_dynamodb()
    config_data = {
        "match": {
            "instance-id": instance_maps.keys()
        },
        "snapshot": {
            "retention": "4 days",
            "minimum": 5,
            "frequency": "12 hours"
        }
    }
    dynamo.store_configuration('some_unique_id', '111122223333', config_data)

    # patch the final message sender method
    mocker.patch('ebs_snapper_lambda_v2.snapshot.send_fanout_message')

    # fan out, and be sure we touched every instance we created before
    snapshot.perform_fanout_all_regions()

    for key, value in instance_maps.iteritems():
        snapshot.send_fanout_message.assert_any_call(  # pylint: disable=E1103
            instance_id=key,
            region=value,
            topic_arn=expected_sns_topic,
            snapshot_settings=config_data["snapshot"])


def test_perform_snapshot():
    """Test for method of the same name."""
    # TBD: needs to be implemented still in snapshot module
    pass
