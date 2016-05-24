# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for testing clean module."""

import json
import datetime
from datetime import timedelta
import dateutil
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


@mock_ec2
def test_clean_snapshot(mocker):
    """Test for method of the same name."""
    # def clean_snapshot(region):
    region = 'us-east-1'
    owner_ids = utils.get_owner_id()

    # mock the over-arching method that just loops over the last 10 days
    mocker.patch('ebs_snapper_lambda_v2.clean.clean_snapshots_tagged')
    clean.clean_snapshot(region)

    # be sure we call deletes for multiple days
    delete_on = datetime.date.today()
    for i in range(0, 10):
        clean.clean_snapshots_tagged.assert_any_call(  # pylint: disable=E1103
            delete_on + timedelta(days=-i),
            owner_ids,
            region)


@mock_ec2
def test_clean_snapshots_tagged(mocker):
    """Test for method of the same name."""
    # default settings
    region = 'us-east-1'

    # create an instance and record the id
    instance_id = mocks.create_instances(region, count=1)[0]
    owner_ids = utils.get_owner_id()

    # figure out the EBS volume that came with our instance
    volume_id = utils.get_volumes(instance_id, region)[0]

    # make a snapshot that should be deleted today too
    now = datetime.datetime.now(dateutil.tz.tzutc())
    delete_on = now.strftime('%Y-%m-%d')
    utils.snapshot_and_tag(volume_id, delete_on, region)
    snapshot_id = utils.most_recent_snapshot(volume_id, region)['SnapshotId']

    mocker.patch('ebs_snapper_lambda_v2.utils.delete_snapshot')
    clean.clean_snapshots_tagged(now, owner_ids, region)

    # ensure we deleted this snapshot if it was ready to die today
    utils.delete_snapshot.assert_any_call(snapshot_id, region)  # pylint: disable=E1103
