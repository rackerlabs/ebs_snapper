# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing snapshot module."""

from __future__ import print_function
import json
from moto import mock_dynamodb2
from moto import mock_ec2
import boto3
from ebs_snapper_lambda_v2 import dynamo


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
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.create_table(
        TableName='ebs_snapshot_configuration',
        KeySchema=[
            {
                'AttributeName': 'aws_account_id',
                'KeyType': 'HASH'
            },
            {
                'AttributeName': 'id',
                'KeyType': 'RANGE'
            }
        ],
        AttributeDefinitions=[
            {
                "AttributeName": "aws_account_id",
                "AttributeType": "S"
            },
            {
                "AttributeName": "id",
                "AttributeType": "S"
            }
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 10,
            'WriteCapacityUnits': 10
        }
    )

    # make sure we successfully created the table
    table = dynamodb.Table('ebs_snapshot_configuration')
    assert table.table_status == "ACTIVE"

    # put some data in
    config_data = {
        "match": {
            "instance_id": "i-abc12345",
            "instance_tag": "special_flower",
            "instance_name": "legacy_server"
        },
        "snapshot": {
            "retention": "4 days",
            "minimum": 5,
            "frequency": "12 hours"
        }
    }

    # put it in the table, be sure it succeeded
    response = table.put_item(
        Item={
            'aws_account_id': '111122223333',
            'id': 'foo',
            'configuration': json.dumps(config_data)
        }
    )
    assert 'configuration' in response.get('Attributes', {})

    fetched_configurations = dynamo.fetch_configurations()
    assert fetched_configurations == [config_data]
