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
"""Module for accessing DynamoDB configuration data."""

from __future__ import print_function
import json
import boto3
from boto3.dynamodb.conditions import Key
from ebs_snapper import utils


def list_ids(context, installed_region, aws_account_id=None):
    """Retrieve configuration from DynamoDB and return array of dictionary objects"""
    found_configurations = {}
    if aws_account_id is None:
        aws_account_id = utils.get_owner_id(context)[0]

    dynamodb = boto3.resource('dynamodb', region_name=installed_region)
    table = dynamodb.Table('ebs_snapshot_configuration')

    results = table.query(
        KeyConditionExpression=Key('aws_account_id').eq(aws_account_id)
    )

    for item in results['Items']:
        str_item = item['configuration']
        found_configurations[str_item] = item['id']

    return found_configurations.values()


def list_configurations(context, installed_region, aws_account_id=None):
    """Retrieve configuration from DynamoDB and return array of dictionary objects"""
    found_configurations = {}
    if aws_account_id is None:
        aws_account_id = utils.get_owner_id(context)[0]

    dynamodb = boto3.resource('dynamodb', region_name=installed_region)
    table = dynamodb.Table('ebs_snapshot_configuration')

    results = table.query(
        KeyConditionExpression=Key('aws_account_id').eq(aws_account_id)
    )

    for item in results['Items']:
        str_item = item['configuration']
        json_item = json.loads(str_item)
        found_configurations[str_item] = json_item

    return found_configurations.values()


def get_configuration(context, installed_region, object_id, aws_account_id=None):
    """Retrieve configuration from DynamoDB and return single object"""
    if aws_account_id is None:
        aws_account_id = utils.get_owner_id(context)[0]

    dynamodb = boto3.resource('dynamodb', region_name=installed_region)
    table = dynamodb.Table('ebs_snapshot_configuration')

    expr = Key('aws_account_id').eq(aws_account_id) & Key('id').eq(object_id)
    results = table.query(KeyConditionExpression=expr)

    for item in results['Items']:
        str_item = item['configuration']
        json_item = json.loads(str_item)
        return json_item

    return None


def store_configuration(installed_region, object_id, aws_account_id, configuration):
    """Function to store configuration item"""
    dynamodb = boto3.resource('dynamodb', region_name=installed_region)
    table = dynamodb.Table('ebs_snapshot_configuration')

    # be sure they parse correctly before we go saving them
    utils.parse_snapshot_settings(configuration)

    response = table.put_item(
        Item={
            'aws_account_id': aws_account_id,
            'id': object_id,
            'configuration': json.dumps(configuration)
        }
    )

    return response.get('Attributes', {})


def delete_configuration(installed_region, object_id, aws_account_id):
    """Function to delete configuration item"""
    dynamodb = boto3.resource('dynamodb', region_name=installed_region)
    table = dynamodb.Table('ebs_snapshot_configuration')

    response = table.delete_item(
        Key={
            'aws_account_id': aws_account_id,
            'id': object_id
        }
    )

    return response.get('Attributes', {})
