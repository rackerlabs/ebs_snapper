# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing clean module."""

import boto3
from moto import mock_ec2, mock_sns
from ebs_snapper_lambda_v2 import clean
from ebs_snapper_lambda_v2 import utils


@mock_ec2
def test_perform_fanout_all_regions():
    """Test for method of the same name."""

    expected_regions = utils.get_regions()

    # capture what the perform_fanout_all_regions method does using an array
    fanned_out_results = []

    def append_region(region):
        """dummy function"""
        fanned_out_results.append(region)
        return fanned_out_results

    # fan out, and be sure we touched every region
    clean.perform_fanout_all_regions(append_region)
    for r in expected_regions:
        assert r in fanned_out_results


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
    # message = json.dumps({'region': region})
    clean.send_fanout_message(region='us-west-2', topic_arn=topic_arn)


def test_print_fanout_message():
    """Test for method of the same name."""
    # Won't test -- this method literally just calls print()
    pass


def test_clean_snapshot():
    """Test for method of the same name."""
    # TBD: needs to be implemented still in snapshot module
    pass
