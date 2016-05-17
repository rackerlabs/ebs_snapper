# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for accessing DynamoDB configuration data."""

from __future__ import print_function
import json
import boto3
from boto3.dynamodb.conditions import Key
from ebs_snapper_lambda_v2 import utils


def fetch_configurations():
    """Retrieve configuration from DynamoDB and return array of dictionary objects"""
    found_configurations = {}
    owner_id = utils.get_owner_id()[0]

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ebs_snapshot_configuration')

    results = table.query(
        KeyConditionExpression=Key('aws_account_id').eq(owner_id)
    )

    for item in results['Items']:
        str_item = item['configuration']
        json_item = json.loads(str_item)
        found_configurations[str_item] = json_item

    return found_configurations.values()
