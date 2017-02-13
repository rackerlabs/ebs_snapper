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
import random
import datetime
from datetime import timedelta
from multiprocessing.pool import ThreadPool
import functools
from time import sleep
import dateutil
import boto3
from crontab import CronTab
from pytimeparse.timeparse import timeparse
import ebs_snapper

LOG = logging.getLogger()
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


def get_owner_id(context, region=None):
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


def build_ignore_list(configurations):
    """Given a bunch of configs, build a list of ids to ignore"""
    ignore_ids = []
    for config in configurations:
        # if it's missing the match section, ignore it
        if not validate_snapshot_settings(config):
            continue

        ignored = config.get('ignore', [])
        ignore_ids.extend(ignored)

    return ignore_ids


def ignore_retention_enabled(configurations):
    """Given a bunch of configs, check for special 'ignore retention' flag"""
    for config in configurations:
        ignored = config.get('ignore_retention', False)
        return bool(ignored)

    return False


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

    ret_s = snapshot_settings['snapshot']['retention']
    retention = timeparse('7 days')
    try:
        retention_seconds = timeparse(ret_s)
        retention = timedelta(seconds=retention_seconds)
    except:
        raise Exception('Could not parse snapshot retention value', ret_s)

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

    LOG.debug('Finished snapshot in %s of volume %s, valid until %s',
              region, volume_id, delete_on)


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
        {'Name': 'attachment.instance-id', 'Values': instance_ids}
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


def build_cache_maps(context, configurations, region, installed_region):
    """Build a giant cache of instances, volumes, snapshots for region"""
    LOG.info("Building cache of instance, volume, and snapshots in %s",
             region)
    LOG.info("This may take a while...")
    cache_data = {
        # calculated here locally
        'instance_id_to_data': {},
        'instance_id_to_config': {},
        'volume_id_to_instance_id': {},

        # calculated w/ multiprocessing module
        'snapshot_id_to_data': {},
        'volume_id_to_snapshot_count': {},
        'volume_id_to_most_recent_snapshot_date': {},
    }

    # build an EC2 client, we're going to need it
    ec2 = boto3.client('ec2', region_name=region)

    if len(configurations) <= 0:
        LOG.info('No configurations found in %s, not building cache', region)
        return cache_data

    # populate them
    LOG.info("Retrieved %s DynamoDB configurations for caching",
             str(len(configurations)))

    # build a list of any IDs (anywhere) that we should ignore
    ignore_ids = build_ignore_list(configurations)

    for config in configurations:
        # stop if we're running out of time
        if ebs_snapper.timeout_check(context, 'build_cache_maps'):
            break

        # if it's missing the match section, ignore it
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

        filters.append({'Name': 'instance-state-name',
                        'Values': ['running', 'stopped']})
        instances = ec2.describe_instances(Filters=filters)
        res_list = instances.get('Reservations', [])
        random.shuffle(res_list)  # attempt to randomize order, for timeouts

        for reservation in res_list:
            inst_list = reservation.get('Instances', [])
            random.shuffle(inst_list)  # attempt to randomize order, for timeouts

            for instance_data in inst_list:
                instance_id = instance_data['InstanceId']

                # skip if we're ignoring this
                if instance_id in ignore_ids:
                    continue

                cache_data['instance_id_to_config'][instance_id] = config
                cache_data['instance_id_to_data'][instance_id] = instance_data
                for dev in instance_data.get('BlockDeviceMappings', []):
                    vid = dev['Ebs']['VolumeId']

                    # skip if we're ignoring this
                    if vid in ignore_ids:
                        continue

                    cache_data['volume_id_to_instance_id'][vid] = instance_id

    LOG.info("Retrieved %s instances for caching",
             str(len(cache_data['instance_id_to_data'].keys())))

    # look at each volume, get snapshots and count / most recent, and map to instance
    process_volumes = cache_data['volume_id_to_instance_id'].keys()[:]
    LOG.info("Retrieved %s volumes for caching",
             str(len(process_volumes)))

    chunked_work = []
    while len(process_volumes) > 0:
        popped = process_volumes[:25]
        del process_volumes[:25]
        chunked_work.append(popped)

    LOG.debug('Split out volume work into %s lists, pulling snapshots...',
              str(len(chunked_work)))

    if len(chunked_work) > 0:
        f = functools.partial(chunk_volume_work, region)
        pool = ThreadPool(processes=4)
        results = pool.map(f, chunked_work)
        pool.close()
        pool.join()

        keys = ['volume_id_to_most_recent_snapshot_date',
                'volume_id_to_snapshot_count',
                'snapshot_id_to_data']
        for result_chunk in results:
            for k in keys:
                cache_data[k].update(result_chunk[k])

    LOG.info("Retrieved %s snapshots for caching",
             str(len(cache_data['snapshot_id_to_data'])))

    return cache_data


def chunk_volume_work(region, volume_list):
    """Used to multiprocess fanout fetching snapshots for volumes"""
    volume_id_to_most_recent_snapshot_date = {}
    volume_id_to_snapshot_count = {}
    snapshot_id_to_data = {}
    LOG.debug("Pulling snapshots for: %s", str(volume_list))

    session = boto3.session.Session(region_name=region)
    ec2 = session.client('ec2')

    paginator = ec2.get_paginator('describe_snapshots')
    operation_parameters = {'Filters': [
        {'Name': 'volume-id', 'Values': volume_list}
    ]}
    page_iterator = paginator.paginate(**operation_parameters)

    for page in page_iterator:
        for snap in page['Snapshots']:
            # just save it
            snapshot_id_to_data[snap['SnapshotId']] = snap

            vid = snap['VolumeId']
            pre_ct = volume_id_to_snapshot_count.get(vid, 0)
            pre_ct += 1
            volume_id_to_snapshot_count[vid] = pre_ct

            pre_date = volume_id_to_most_recent_snapshot_date.get(vid, None)
            cur_date = snap['StartTime']
            if pre_date is None:
                volume_id_to_most_recent_snapshot_date[vid] = cur_date
            elif cur_date > pre_date:
                volume_id_to_most_recent_snapshot_date[vid] = cur_date

    return {
        'volume_id_to_most_recent_snapshot_date': volume_id_to_most_recent_snapshot_date,
        'volume_id_to_snapshot_count': volume_id_to_snapshot_count,
        'snapshot_id_to_data': snapshot_id_to_data
    }


class MockContext(object):
    """Context object when we're not running in lambda"""
    # Useful information about the LambdaContext object
    # https://gist.github.com/gene1wood/c0d37dfcb598fc133a8c

    def __init__(self):
        # session end timer (max lambda)
        five_minutes = datetime.timedelta(minutes=5)
        self.finish_time = datetime.datetime.now(dateutil.tz.tzutc()) + five_minutes

        # called to figure out owner
        self.invoked_function_arn = None

    def set_remaining_time_in_millis(self, remaining_millis):
        """set the remaining time, for mocks"""
        now = datetime.datetime.now(dateutil.tz.tzutc())
        self.finish_time = now + datetime.timedelta(milliseconds=remaining_millis)

    def get_remaining_time_in_millis(self):
        """Return 5 minutes minus remaining time"""
        now = datetime.datetime.now(dateutil.tz.tzutc())
        time_left = self.timedelta_milliseconds(self.finish_time - now)

        if time_left < 0:
            return 0
        else:
            return time_left

    @staticmethod
    def timedelta_milliseconds(td):
        """return milliseconds from a timedelta"""
        return td.days*86400000 + td.seconds*1000 + td.microseconds/1000
