# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing clean module."""

import json
from moto import mock_ec2, mock_sns
from ebs_snapper_lambda_v2 import clean, utils, mocks


@mock_ec2
@mock_sns
def test_perform_fanout_all_regions_clean(mocker):
    """Test for method of the same name."""
    mocks.create_sns_topic('CleanSnapshotTopic')

    expected_regions = utils.get_regions()
    expected_sns_topic = utils.get_topic_arn('CleanSnapshotTopic')

    mocker.patch('ebs_snapper_lambda_v2.clean.send_fanout_message')

    # fan out, and be sure we touched every region
    clean.perform_fanout_all_regions()

    for r in expected_regions:
        clean.send_fanout_message.assert_any_call(  # pylint: disable=E1103
            region=r,
            topic_arn=expected_sns_topic)


@mock_ec2
@mock_sns
def test_send_fanout_message_clean(mocker):
    """Test for method of the same name."""

    mocks.create_sns_topic('testing-topic')
    expected_sns_topic = utils.get_topic_arn('testing-topic')

    mocker.patch('ebs_snapper_lambda_v2.utils.sns_publish')
    clean.send_fanout_message(region='us-west-2', topic_arn=expected_sns_topic)
    utils.sns_publish.assert_any_call(  # pylint: disable=E1103
        TopicArn=expected_sns_topic,
        Message=json.dumps({'region': 'us-west-2'}))


def test_clean_snapshot():
    """Test for method of the same name."""
    # TBD: needs to be implemented still in clean module
    pass
