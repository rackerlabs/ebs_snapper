# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.
"""Module for utility functions."""

from __future__ import print_function
import boto3


def get_owner_id():
    """Get overall owner account id by finding an AWS instance"""
    regions = get_regions(must_contain_instances=True)
    for region in regions:
        client = boto3.client('ec2', region_name=region)
        instances = client.describe_instances()
        return list(set([x['OwnerId'] for x in instances['Reservations']]))


def get_regions(must_contain_instances=False):
    """Get regions, optionally filtering by regions containing instances."""
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


def apply_instances(region, func):
    """Call func with all instance_id's in region."""
    client = boto3.client('ec2', region_name=region)
    instances = client.describe_instances(
        Filters=[{'Name': 'instance-state-name',
                  'Values': ['running', 'stopped']}]
        )

    for reservation in instances.get('Reservations', []):
        for instance in reservation.get('Instances', []):
            func(instance['InstanceId'])


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
