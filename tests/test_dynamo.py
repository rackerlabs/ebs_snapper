# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing snapshot module."""

from __future__ import print_function
import pytest
from moto import mock_dynamodb2
from moto import mock_ec2
import boto3
from ebs_snapper_lambda_v2 import dynamo, mocks


@mock_ec2
@mock_dynamodb2
def test_fetch_missing_configurations():
    """Test for method of the same name."""

    # region for our tests
    region = 'us-east-1'

    # create dummy ec2 instance so we can figure out account id
    client = boto3.client('ec2', region_name=region)
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    with pytest.raises(Exception):
        # make sure we successfully created the table
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table('ebs_snapshot_configuration')
        assert table.table_status == "ACTIVE"

        dynamo.fetch_configurations()


@mock_ec2
@mock_dynamodb2
def test_fetch_configurations():
    """Test for method of the same name."""

    # region for our tests
    region = 'us-east-1'

    # create dummy ec2 instance so we can figure out account id
    client = boto3.client('ec2', region_name=region)
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # create a mock table
    mocks.create_dynamodb(region=region)

    # make sure we successfully created the table
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table('ebs_snapshot_configuration')
    assert table.table_status == "ACTIVE"

    # put some data in
    config_data = {
        "match": {
            "instance-id": "i-abc12345",
            "tag:plant": "special_flower",
            "tag:Name": "legacy_server"
        },
        "snapshot": {
            "retention": "6 days",
            "minimum": 6,
            "frequency": "13 hours"
        }
    }

    # put it in the table, be sure it succeeded
    response = dynamo.store_configuration('foo', '111122223333', config_data)
    assert response != {}

    fetched_configurations = dynamo.fetch_configurations()
    assert fetched_configurations == [config_data]
