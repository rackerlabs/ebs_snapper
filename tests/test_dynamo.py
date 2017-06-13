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
"""Module for testing snapshot module."""

from __future__ import print_function
import pytest
from moto import mock_dynamodb2
from moto import mock_ec2, mock_sts, mock_iam
import boto3
from ebs_snapper import dynamo, mocks, utils
from ebs_snapper import EbsSnapperError, AWS_MOCK_ACCOUNT


def setup_module(module):
    import logging
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO)


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_list_missing_configurations():
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

        dynamo.list_configurations(region)


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_configurations():
    """Test for method for get, fetch, delete."""

    # region for our tests
    region = 'us-east-1'

    # create dummy ec2 instance so we can figure out account id
    client = boto3.client('ec2', region_name=region)
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)

    # create a mock table
    mocks.create_dynamodb(region)
    ctx = utils.MockContext()

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
    response = dynamo.store_configuration(region, 'foo', AWS_MOCK_ACCOUNT, config_data)
    assert response != {}

    # now list everything, be sure it was present
    fetched_configurations = dynamo.list_configurations(ctx, region, AWS_MOCK_ACCOUNT)
    assert fetched_configurations == [config_data]

    # now get that specific one
    specific_config = dynamo.get_configuration(ctx, region, 'foo', AWS_MOCK_ACCOUNT)
    assert specific_config == config_data

    # be sure another get for invalid item returns none
    missing_config = dynamo.get_configuration(ctx, region, 'abc', AWS_MOCK_ACCOUNT)
    assert missing_config is None

    # be sure it returns in a list
    fetched_configurations = dynamo.list_ids(ctx, region)
    assert 'foo' in fetched_configurations

    # now delete it and confirm both list and get return nothing
    dynamo.delete_configuration(region, 'foo', AWS_MOCK_ACCOUNT)
    specific_config = dynamo.get_configuration(ctx, region, 'foo', AWS_MOCK_ACCOUNT)
    assert specific_config is None
    fetched_configurations = dynamo.list_configurations(ctx, region)
    assert fetched_configurations == []


@mock_ec2
@mock_dynamodb2
@mock_iam
@mock_sts
def test_store_bad_configuration():
    """Test for storing a bad config."""

    # region for our tests
    region = 'us-east-1'

    # create dummy ec2 instance so we can figure out account id
    client = boto3.client('ec2', region_name=region)
    client.run_instances(ImageId='ami-123abc', MinCount=1, MaxCount=5)
    aws_account_id = AWS_MOCK_ACCOUNT
    object_id = 'foo'

    # create a mock table
    mocks.create_dynamodb(region)
    ctx = utils.MockContext()

    # make sure we successfully created the table
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table('ebs_snapshot_configuration')
    assert table.table_status == "ACTIVE"

    # put some bad data in
    config_data = {
        "match_bad_name": {
            "instance-id": "i-abc12345",
            "tag:plant": "special_flower",
            "tag:Name": "legacy_server"
        }
    }

    # this should blow up
    with pytest.raises(Exception):
        dynamo.store_configuration(region, object_id, aws_account_id, config_data)

    # now force it
    table.put_item(
        Item={
            'aws_account_id': aws_account_id,
            'id': object_id,
            'configuration': "{, 123 bare words :: }"
        }
    )

    # now watch it blow up on listing them
    with pytest.raises(EbsSnapperError):
        dynamo.list_configurations(ctx, region, aws_account_id)

    # now blow up on fetching a specific one by Key
    with pytest.raises(EbsSnapperError):
        dynamo.get_configuration(ctx, region, object_id, aws_account_id)
