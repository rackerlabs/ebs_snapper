# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for utility functions."""

from __future__ import print_function
import logging
import boto3

LOG = logging.getLogger(__name__)


def get_owner_id():
    """Get overall owner account id by finding an AWS instance"""
    LOG.debug('get_owner_id')
    regions = get_regions(must_contain_instances=True)
    for region in regions:
        client = boto3.client('ec2', region_name=region)
        instances = client.describe_instances()
        return list(set([x['OwnerId'] for x in instances['Reservations']]))


def get_regions(must_contain_instances=False):
    """Get regions, optionally filtering by regions containing instances."""
    LOG.debug('get_regions(must_contain_instances=%s)', must_contain_instances)
    client = boto3.client('ec2', region_name='us-east-1')
    regions = client.describe_regions()
    region_names = [x['RegionName'] for x in regions['Regions']]

    if must_contain_instances:
        return [x for x in region_names if region_contains_instances(x)]
    else:
        return region_names


def region_contains_instances(region):
    """Check if a region contains EC2 instances"""
    client = boto3.client('ec2', region_name=region)
    instances = client.describe_instances(
        Filters=[{'Name': 'instance-state-name',
                  'Values': ['running', 'stopped']}]
    )
    return 'Reservations' in instances and len(instances['Reservations']) > 0


def get_topic_arn(topic_name):
    """Search for an SNS topic containing topic_name."""
    regions = get_regions()
    for region in regions:
        client = boto3.client('sns', region_name=region)
        topics = client.list_topics()
        for topic in topics['Topics']:
            splits = topic['TopicArn'].split(':')
            if splits[5] == topic_name:
                return topic['TopicArn']
    raise Exception('Could not find an SNS topic {}'.format(topic_name))


def convert_configurations_to_boto_filter(configuration):
    """Convert JSON settings format to boto3-friendly filter"""
    results = []

    for key, value in configuration.iteritems():
        f = {
            'Name': key,
            'Values': flatten([value])
        }
        results.append(f)

    return results


def sns_publish(TopicArn, Message):
    """Wrapper around SNS client so we can mock and unit test and assert it"""
    sns_client = boto3.client('sns')
    sns_client.publish(TopicArn=TopicArn, Message=Message)


def flatten(l):
    """Flatten, like in ruby"""
    return flatten(l[0]) + (flatten(l[1:]) if len(l) > 1 else []) if type(l) is list else [l]
