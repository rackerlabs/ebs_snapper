# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for accessing DynamoDB configuration data."""

from __future__ import print_function
import json
import boto3
from boto3.dynamodb.conditions import Key
from ebs_snapper_lambda_v2 import utils


def list_configurations():
    """Retrieve configuration from DynamoDB and return array of dictionary objects"""
    found_configurations = {}
    aws_account_id = utils.get_owner_id()[0]

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ebs_snapshot_configuration')

    results = table.query(
        KeyConditionExpression=Key('aws_account_id').eq(aws_account_id)
    )

    for item in results['Items']:
        str_item = item['configuration']
        json_item = json.loads(str_item)
        found_configurations[str_item] = json_item

    return found_configurations.values()


def get_configuration(object_id, aws_account_id=None):
    """Retrieve configuration from DynamoDB and return single object"""
    if aws_account_id is None:
        aws_account_id = utils.get_owner_id()[0]

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ebs_snapshot_configuration')

    expr = Key('aws_account_id').eq(aws_account_id) & Key('id').eq(object_id)
    results = table.query(KeyConditionExpression=expr)

    for item in results['Items']:
        str_item = item['configuration']
        json_item = json.loads(str_item)
        return json_item

    return None


def store_configuration(object_id, aws_account_id, configuration):
    """Function to store configuration item"""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ebs_snapshot_configuration')

    response = table.put_item(
        Item={
            'aws_account_id': aws_account_id,
            'id': object_id,
            'configuration': json.dumps(configuration)
        }
    )

    return response.get('Attributes', {})


def delete_configuration(object_id, aws_account_id):
    """Function to delete configuration item"""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ebs_snapshot_configuration')

    response = table.delete_item(
        Key={
            'aws_account_id': aws_account_id,
            'id': object_id
        }
    )

    return response.get('Attributes', {})
