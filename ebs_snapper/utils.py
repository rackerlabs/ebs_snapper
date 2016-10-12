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
"""Module for utility functions."""

from __future__ import print_function
import logging
import collections
from time import sleep
from datetime import timedelta
import dateutil
import boto3
from pytimeparse.timeparse import timeparse
from crontab import CronTab
import ebs_snapper

LOG = logging.getLogger(__name__)
AWS_TAGS = [
    "Name",
    "BusinessUnit", "Group",
    "Department", "CostCenter",
    "Application", "Environment", "Project",
    "Owner", "Service",
    "Cluster", "Role", "Customer", "Version",
    "Billing1", "Billing2", "Billing3", "Billing4", "Billing5"
]
SNAP_DESC_TEMPLATE = "Created from {0} by EbsSnapper({3}) for {1} from {2}"
ALLOWED_SNAPSHOT_DELETE_FAILURES = ['InvalidSnapshot.InUse', 'InvalidSnapshot.NotFound']


def get_owner_id(region=None, context=None):
    """Get overall owner account id using a bunch of tricks"""
    LOG.debug('get_owner_id')

    # see if Lambda context is non-None
    try:
        if context is not None:
            LOG.debug('get_owner_id: Lambda')
            return [context.invoked_function_arn.split(':')[4]]
    except:
        pass

    # maybe STS can tell us?
    try:
        LOG.debug('get_owner_id: STS')
        sts_client = boto3.client('sts')
        account_id = sts_client.get_caller_identity()["Account"]
        return [str(account_id)]
    except:
        pass

    # maybe we can look at another user's arn?
    try:
        LOG.debug('get_owner_id: STS another user')
        iam_client = boto3.client('iam')
        return [iam_client.list_users(MaxItems=1)["Users"][0]["Arn"].split(':')[4]]
    except:
        pass

    # maybe we have API keys from boto3?
    try:
        LOG.debug('get_owner_id: IAM')
        iam_client = boto3.client('iam')
        return [iam_client.get_user()['User']['Arn'].split(':')[4]]
    except:
        pass

    # if we're _inside_ an EC2 instance
    try:
        LOG.debug('get_owner_id: EC2 Metadata Service')
        from botocore.vendored import requests
        s_url = 'http://169.254.169.254/latest/meta-data/iam/info/'
        return [requests.get(s_url, timeout=1).json()['InstanceProfileArn'].split(':')[4]]
    except:
        pass

    # try using EC2 instances with account_ids for owners
    if region is not None:
        LOG.debug('get_owner_id: EC2 region %s', region)
        regions = [region]
    else:
        LOG.debug('get_owner_id: EC2 all regions')
        regions = get_regions(must_contain_instances=True)

    owners = []
    for region in regions:
        client = boto3.client('ec2', region_name=region)
        instances = client.describe_instances()
        owners.extend([x['OwnerId'] for x in instances['Reservations']])

    return list(set(owners))


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


def get_topic_arn(topic_name, default_region='us-east-1'):
    """Search for an SNS topic containing topic_name."""

    client = boto3.client('sns', region_name=default_region)
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


def sns_publish(TopicArn, Message, Region='us-east-1'):
    """Wrapper around SNS client so we can mock and unit test and assert it"""
    client = boto3.client('sns', region_name=Region)
    client.publish(TopicArn=TopicArn, Message=Message)


def flatten(l):
    """Flatten, like in ruby"""
    return flatten(l[0]) + (flatten(l[1:]) if len(l) > 1 else []) if type(l) is list else [l]


def parse_snapshot_settings(snapshot_settings):
    """convert JSON snapshot settings to timedeltas"""

    # validate keys are present
    expected_keys = ['retention', 'minimum', 'frequency']
    for k in expected_keys:
        if k not in snapshot_settings['snapshot']:
            raise Exception('missing required snapshot setting {}'.format(k))

    retention_seconds = timeparse(snapshot_settings['snapshot']['retention'])
    retention = timedelta(seconds=retention_seconds)

    f_expr = snapshot_settings['snapshot']['frequency']
    if is_timedelta_expression(f_expr):
        frequency_seconds = timeparse(f_expr)
        return retention, timedelta(seconds=frequency_seconds)
    elif is_crontab_expression(f_expr):
        return retention, CronTab(f_expr)
    else:
        raise Exception('Could not identify expression', f_expr)


def validate_snapshot_settings(snapshot_settings):
    """Validate snapshot settings JSON"""
    if 'match' not in snapshot_settings or 'snapshot' not in snapshot_settings:
        LOG.warn(
            'Configuration is missing a match/snapshot, will not use it for snapshots: %s',
            str(snapshot_settings))
        return False

    # validate keys are present
    expected_keys = ['retention', 'minimum', 'frequency']
    for k in expected_keys:
        if k not in snapshot_settings['snapshot']:
            LOG.warn(
                'Configuration is missing %s, will not use it for snapshots: %s',
                k,
                str(snapshot_settings))
            return False

    return True


def get_instance(instance_id, region):
    """find and return the data about a single instance"""
    ec2 = boto3.client('ec2', region_name=region)
    instance_data = ec2.describe_instances(InstanceIds=[instance_id])
    if 'Reservations' not in instance_data:
        raise Exception('Response missing reservations %s', instance_data)

    reservations = instance_data['Reservations']
    instances = sum([[i for i in r['Instances']] for r in reservations], [])
    if not len(instances) == 1:
        raise Exception('Found too many instances for this id %s', instances)

    return instances[0]


def count_snapshots(volume_id, region):
    """count how many snapshots exist for this volume"""
    count = 0

    page_iterator = build_snapshot_paginator([volume_id], region)
    for page in page_iterator:
        count += len(page['Snapshots'])

    return count


def most_recent_snapshot(volume_id, region):
    """find and return the most recent snapshot"""
    recent = {}

    page_iterator = build_snapshot_paginator([volume_id], region)
    for page in page_iterator:
        for s in page['Snapshots']:
            if recent == {} or recent['StartTime'] < s['StartTime']:
                recent = s

    if 'StartTime' in recent:
        return recent

    return None


def get_snapshots_by_volume(volume_id, region):
    """Return snapshots by volume and region"""
    snapshot_list = []

    page_iterator = build_snapshot_paginator([volume_id], region)
    for page in page_iterator:
        for s in page['Snapshots']:
            snapshot_list.append(s)

    return snapshot_list


def get_snapshots_by_volumes(volume_list, region):
    """Return snapshots by volume and region"""
    snapshot_list = []

    page_iterator = build_snapshot_paginator(volume_list, region)
    for page in page_iterator:
        for s in page['Snapshots']:
            snapshot_list.append(s)

    return snapshot_list


def build_snapshot_paginator(volume_list, region):
    """Utility function to make pagination of snapshots easier"""
    ec2 = boto3.client('ec2', region_name=region)

    paginator = ec2.get_paginator('describe_snapshots')
    operation_parameters = {'Filters': [
        {'Name': 'volume-id', 'Values': volume_list}
    ]}
    sleep(1)  # help w/ API limits
    return paginator.paginate(**operation_parameters)


def snapshot_and_tag(instance_id, ami_id, volume_id, delete_on, region, additional_tags=None):
    """Create snapshot and retention tag"""

    LOG.warn('Creating snapshot in %s of volume %s, valid until %s',
             region, volume_id, delete_on)

    snapshot_description = SNAP_DESC_TEMPLATE.format(
        instance_id,
        ami_id,
        volume_id,
        ebs_snapper.__version__
    )

    full_tags = [{'Key': 'DeleteOn', 'Value': delete_on}]
    if additional_tags is not None:
        # we only get 10 tags, so restrict additional_tags to nine
        full_tags.extend(additional_tags[:9])

    ec2 = boto3.client('ec2', region_name=region)

    snapshot = ec2.create_snapshot(
        VolumeId=volume_id,
        Description=snapshot_description[0:254]
    )

    ec2.create_tags(
        Resources=[snapshot['SnapshotId']],
        Tags=full_tags
    )


def delete_snapshot(snapshot_id, region):
    """Simple wrapper around deletes so we can mock them"""
    ec2 = boto3.client('ec2', region_name=region)
    try:
        ec2.delete_snapshot(SnapshotId=snapshot_id)
    except Exception as e:
        LOG.warn('Failed to remove snapshot %s in region %s: %s',
                 snapshot_id, region, str(e))

        # if an error is okay, we'll emit the log but not blow up
        for allowed_err in ALLOWED_SNAPSHOT_DELETE_FAILURES:
            if allowed_err in str(e):
                return 0

        # an error that isn't whitelisted, throw an Exception
        raise

    # a success if it wasn't the whitelist
    return 1


def get_volumes(instance_ids, region):
    """Get volumes from instance id"""

    volumes = []
    filters_for_instances = [
        {'Name': 'attachment.instance-id', 'Values':instance_ids}
    ]

    ec2 = boto3.client('ec2', region_name=region)
    vol_paginator = ec2.get_paginator('describe_volumes')
    operation_parameters = {'Filters': filters_for_instances}

    # paginate -- there might be a lot of tags
    for page in vol_paginator.paginate(**operation_parameters):
        # if we don't get even a page of results, or missing hash key, skip
        if not page and 'Volumes' not in page:
            continue

        # iterate over each 'Tags' entry
        for volume in page.get('Volumes', []):
            volumes.append(volume)

    return volumes


def get_volume(volume_id, region):
    """find and return the data about a single instance"""
    ec2 = boto3.client('ec2', region_name=region)
    volume_data = ec2.describe_volumes(VolumeIds=[volume_id])
    if 'Volumes' not in volume_data:
        raise Exception('Response missing volumes %s', volume_data)

    volumes = volume_data['Volumes']
    if not len(volumes) == 1:
        raise Exception('Found too many volumes for this id %s', volumes)

    return volumes[0]


def get_instance_by_volume(volume_id, region):
    """Get instance from volume id"""
    ec2 = boto3.client('ec2', region_name=region)

    try:
        found_volumes = ec2.describe_volumes(VolumeIds=[volume_id])
        for volume in found_volumes['Volumes']:
            for attachment in volume['Attachments']:
                return attachment['InstanceId']
    except:
        LOG.warn('Failed to find an instance in %s for volume %s',
                 region, volume_id)

    return None


def get_snapshot_settings_by_instance(instance_id, configurations, region):
    """Given an instance, find the snapshot config that applies"""

    client = boto3.client('ec2', region_name=region)
    for config in configurations:
        if not validate_snapshot_settings(config):
            continue

        # build a boto3 filter to describe instances with
        configuration_matches = config['match']

        filters = convert_configurations_to_boto_filter(configuration_matches)
        # if we ended up with no boto3 filters, we bail so we don't snapshot everything
        if len(filters) <= 0:
            LOG.warn('Could not convert configuration match to a filter: %s',
                     configuration_matches)
            continue

        instances = client.describe_instances(Filters=filters)
        for reservation in instances.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                if instance['InstanceId'] == instance_id:
                    return config

    # No settings were found
    return None


def calculate_relevant_tags(instance_tags, volume_tags, max_results=10):
    """Copy AWS tags from instance to volume to snapshot, per product guide"""

    # ordered dict of tags, because we care about order
    calculated_tags = collections.OrderedDict()

    # go ahead and throw all the billing tags in first
    for billing_tag in AWS_TAGS:
        calculated_tags[billing_tag] = None

    # first figure out any instance tags
    if instance_tags is not None:
        # add relevant ones to the list
        for tag_ds in instance_tags:
            tag_name, tag_value = tag_ds['Key'], tag_ds['Value']
            calculated_tags[tag_name] = tag_value

    # overwrite tag values from instances with volume tags/values
    if volume_tags is not None:
        # add relevant ones to the list
        for tag_ds in volume_tags:
            tag_name, tag_value = tag_ds['Key'], tag_ds['Value']
            calculated_tags[tag_name] = tag_value

    returned_tags = []
    for n, v in calculated_tags.iteritems():
        # skip any tags that were None/falsey, and don't go above max_results
        if not v or len(returned_tags) >= max_results:
            continue

        if 'aws:' in n:
            continue

        returned_tags.append({
            'Key': n,
            'Value': v
        })

    return returned_tags


def is_crontab_expression(expr):
    """True IFF expr is of type CronTab or can be used to create a CronTab"""
    try:
        return isinstance(expr, CronTab) or CronTab(expr) is not None
    except:
        return False

    return False


def is_timedelta_expression(expr):
    """True IFF expr is of type timedelta or can be used to create a timedelta"""
    try:
        return isinstance(expr, timedelta) or timeparse(expr) is not None
    except:
        return False

    return False


def find_deleteon_tags(region_name, cutoff_date, max_tags=10):
    """Get tags before cutoff date on snaps in region, max returned tags"""
    ec2 = boto3.client('ec2', region_name=region_name)
    results_found = []

    filter_for_tags = [{'Name': 'resource-type', 'Values': ['snapshot']},
                       {'Name': 'key', 'Values': ['DeleteOn']}]

    tag_paginator = ec2.get_paginator('describe_tags')
    operation_parameters = {'Filters': filter_for_tags}

    # paginate -- there might be a lot of tags
    for page in tag_paginator.paginate(**operation_parameters):
        # if we don't get even a page of results, or missing hash key, skip
        if not page and 'Tags' not in page:
            continue

        # iterate over each 'Tags' entry
        for found_tag in page.get('Tags', []):

            # don't bother parsing a tag we're already going to return
            if found_tag['Value'] in results_found:
                continue

            # try to understand that tag
            if dateutil.parser.parse(found_tag['Value']).date() <= cutoff_date:
                results_found.append(found_tag['Value'])

            # get out if we ever add an element and go over the max
            if len(results_found) > max_tags:
                break

    # return max values at most, sorted by lexical (oldest!)
    return sorted(results_found[:max_tags])
