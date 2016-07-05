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


def create_dynamodb(installed_region='us-east-1'):
    """Used with moto, create DynamoDB table"""
    dynamodb = boto3.resource('dynamodb', region_name=installed_region)
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


def create_instances(region='us-east-1', count=1):
    """Create some dummy instances and return the instance ids"""

    client = boto3.client('ec2', region_name=region)
    ids = []

    create_results = client.run_instances(ImageId='ami-123abc', MinCount=count, MaxCount=count)
    for created_instance in create_results['Instances']:
        ids.append(created_instance['InstanceId'])

    return ids
