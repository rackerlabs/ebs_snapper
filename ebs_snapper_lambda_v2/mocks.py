# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module that can create mocks for testing."""

from __future__ import print_function
import boto3


def create_sns_topic(topic_name, region_name='us-east-1'):
    """Used with moto, create an SNS topic"""
    # make an SNS topic
    client = boto3.client('sns', region_name=region_name)
    response = client.create_topic(Name=topic_name)

    if not response['ResponseMetadata']['HTTPStatusCode'] == 200:
        raise Exception('Could not create topic {} in region {}'.format(topic_name, region_name))


def create_dynamodb(region='us-east-1'):
    """Used with moto, create DynamoDB table"""
    dynamodb = boto3.resource('dynamodb', region_name=region)
    dynamodb.create_table(
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
