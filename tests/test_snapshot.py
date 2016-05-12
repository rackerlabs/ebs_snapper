# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing snapshot module."""

import boto3
from moto import mock_ec2, mock_sns
from ebs_snapper_lambda_v2 import snapshot


@mock_ec2
def test_perform_fanout_all_regions():
    """Test for method of the same name."""

    dummy_regions = ['us-west-2', 'us-east-1']

    # make some dummy instances in two regions
    instance_maps = {}
    for dummy_region in dummy_regions:
        client = boto3.client('ec2', region_name=dummy_region)
        create_results = client.run_instances(ImageId='ami-123abc', MinCount=5, MaxCount=5)
        for instance_data in create_results['Instances']:
            instance_maps[instance_data['InstanceId']] = dummy_region

    # capture what the perform_fanout_all_regions method does using a hash
    fanned_out_results = {}

    def append_region(item, region):
        """dummy function"""
        fanned_out_results[item] = region
        return fanned_out_results

    # fan out, and be sure we touched every instance we created in every region
    snapshot.perform_fanout_all_regions(append_region)
    assert fanned_out_results == instance_maps


@mock_ec2
def test_perform_fanout_by_region():
    """Test for method of the same name."""
    dummy_region = 'ap-northeast-1'
    client = boto3.client('ec2', region_name=dummy_region)

    instances_created = []
    create_results = client.run_instances(ImageId='ami-123abc', MinCount=5, MaxCount=5)
    for instance_data in create_results['Instances']:
        instances_created.append(instance_data['InstanceId'])

    instances_touched = []

    def append_item(item, region):
        """dummy function"""
        instances_touched.append(item)

    snapshot.perform_fanout_by_region(append_item, dummy_region)
    assert instances_created == instances_touched


@mock_ec2
@mock_sns
def test_send_fanout_message():
    """Test for method of the same name."""
    sns_client = boto3.client('sns', region_name='us-west-2')

    # make an SNS topic
    response = sns_client.create_topic(Name='testing-topic')
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200
    topic_arn = response['TopicArn']

    # TODO: figure out how to mock:
    # <bound method SNS.publish of <botocore.client.SNS object at 0x10adc6190>>
    # message = json.dumps({'instance_id': instance_id, 'region': region})
    snapshot.send_fanout_message(instance_id='i-1234abc', region='us-west-2', topic_arn=topic_arn)


def test_print_fanout_message():
    """Test for method of the same name."""
    # Won't test -- this method literally just calls print()
    pass


def test_perform_snapshot():
    """Test for method of the same name."""
    # TBD: needs to be implemented still in snapshot module
    pass
