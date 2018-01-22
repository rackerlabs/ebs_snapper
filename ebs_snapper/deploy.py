#!/usr/bin/env python
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
"""Script for deploying the entire ebs_snapper tool."""

from __future__ import print_function
import logging
import time
import hashlib
import base64

import boto3
from botocore.exceptions import ClientError
from lambda_uploader import package as lu_package

import ebs_snapper
from ebs_snapper import utils, dynamo

LOG = logging.getLogger()
DEFAULT_REGION = 'us-east-1'
STACK_WAIT_STATUS = ['CREATE_IN_PROGRESS', 'UPDATE_IN_PROGRESS',
                     'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS']
STACK_FATAL_STATUS = ['CREATE_FAILED', 'ROLLBACK_IN_PROGRESS',
                      'ROLLBACK_COMPLETE', 'ROLLBACK_FAILED',
                      'UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE',
                      'UPDATE_ROLLBACK_IN_PROGRESS',
                      'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS']
STACK_SUCCESS_STATUS = ['CREATE_COMPLETE', 'UPDATE_COMPLETE']
IGNORED_UPLOADER_FILES = ["circle.yml", ".git", "/*.pyc", "\\.cache",
                          "\\.json$", "\\.sh$", "\\.zip$"]
DEFAULT_STACK_PARAMS = [
    {'ParameterKey': 'WatchdogRegion',
     'ParameterValue': 'us-east-1', 'UsePreviousValue': False},
    {'ParameterKey': 'CreateScheduleExpression',
     'ParameterValue': 'rate(30 minutes)', 'UsePreviousValue': False},
    {'ParameterKey': 'CleanScheduleExpression',
     'ParameterValue': 'rate(6 hours)', 'UsePreviousValue': False},
    {'ParameterKey': 'ReplicationScheduleExpression',
     'ParameterValue': 'rate(30 minutes)', 'UsePreviousValue': False},
    {'ParameterKey': 'CostCenter',
     'ParameterValue': '', 'UsePreviousValue': False},
    {'ParameterKey': 'LambdaMemoryFanout',
     'ParameterValue': '128', 'UsePreviousValue': False},
    {'ParameterKey': 'LambdaMemorySnapshot',
     'ParameterValue': '256', 'UsePreviousValue': False},
    {'ParameterKey': 'LambdaMemoryClean',
     'ParameterValue': '256', 'UsePreviousValue': False},
    {'ParameterKey': 'LambdaMemoryReplication',
     'ParameterValue': '256', 'UsePreviousValue': False}
]


def deploy(context, aws_account_id=None, no_build=None, no_upload=None, no_stack=None):
    """Main function that does the deploy to an aws account"""
    # lambda-uploader configuration step

    lambda_zip_filename = 'ebs_snapper.zip'
    if not no_build:
        LOG.info("Building package using lambda-uploader")
        build_package(lambda_zip_filename)

    # get security credentials from EC2 API, if we are going to use them
    needs_owner_id = (not no_upload) or (not no_stack)
    if needs_owner_id:
        if aws_account_id is None:
            found_owners = utils.get_owner_id(context)
        else:
            found_owners = [aws_account_id]

        if len(found_owners) <= 0:
            LOG.warn('There are no instances I could find on this account.')
            LOG.warn('I cannot figure out the account number without any instances.')
            LOG.warn('Without account number, I do not know what to name the S3 bucket or stack.')
            LOG.warn('You may provide it on the commandline to bypass this error.')
            return
        else:
            aws_account = found_owners[0]

        # freshen the S3 bucket
        if not no_upload:
            ebs_bucket_name = create_or_update_s3_bucket(aws_account, lambda_zip_filename)

        # freshen the stack
        if not no_stack:
            create_or_update_stack(aws_account, DEFAULT_REGION, ebs_bucket_name)

    # freshen up lambda jobs themselves
    if not no_upload:
        update_function_and_version(ebs_bucket_name, lambda_zip_filename)
        ensure_cloudwatch_logs_retention(aws_account)


def create_or_update_s3_bucket(aws_account, lambda_zip_filename):
    """Ensure the S3 bucket exists, then upload CF and Lambda files"""
    # ensure S3 bucket exists
    s3_client = boto3.client('s3', region_name=DEFAULT_REGION)
    ebs_bucket_name = 'ebs-snapper-{}'.format(aws_account)
    LOG.info("Creating S3 bucket %s if it doesn't exist", ebs_bucket_name)
    s3_client.create_bucket(
        ACL='private',
        Bucket=ebs_bucket_name)

    # upload files to S3 bucket
    LOG.info("Uploading files into S3 bucket")
    upload_files = ['cloudformation.json', lambda_zip_filename]
    for filename in upload_files:

        local_hash = None
        try:
            local_hash = md5sum(filename).strip('"')
        except:
            raise

        try:
            # check if file in bucket is already there and up to date
            object_summary = s3_client.get_object(Bucket=ebs_bucket_name, Key=filename)

            remote_hash = object_summary['ETag'].strip('"')

            LOG.debug("Local file MD5 sum: %s", str(local_hash))
            LOG.debug("ETag from AWS: %s", str(remote_hash))

            if local_hash == remote_hash:
                LOG.info("Skipping upload of %s, already up-to-date in S3", filename)
                continue
        except:
            LOG.info("Failed to checksum remote file %s, uploading it anyway", filename)

        with open(filename, 'rb') as data:
            LOG.info('Uploading %s to bucket %s', filename, ebs_bucket_name)
            s3_client.put_object(Bucket=ebs_bucket_name, Key=filename, Body=data)

    return ebs_bucket_name


def build_package(lambda_zip_filename):
    """Given this project, package it using lambda_uploader"""
    pkg = lu_package.Package('.', lambda_zip_filename)
    pkg.clean_zipfile()

    # lambda-uploader step to build zip file
    pkg.extra_file('ebs_snapper/lambdas.py')
    pkg.requirements('requirements.txt')
    pkg.build(IGNORED_UPLOADER_FILES)
    pkg.clean_workspace()


def wait_for_completion(cf_client, stack_name):
    """Wait for stack to be in a stable, complete status"""
    sleep_timer = 0
    stack_status = None
    while sleep_timer < 20 and stack_status not in STACK_SUCCESS_STATUS:
        time.sleep(6)

        response = cf_client.describe_stacks(StackName=stack_name)

        if 'Stacks' not in response:
            raise Exception('Polling for stack changes failed', response)

        found_stacks = response['Stacks']
        for stack_data in found_stacks:
            if stack_data['StackName'] != stack_name:
                continue

            stack_status = stack_data['StackStatus']
            if stack_status in STACK_FATAL_STATUS:
                raise Exception('Stack creation or update failed', stack_data)
            elif stack_status in STACK_SUCCESS_STATUS:
                LOG.warn('Stack is in a successful state, moving along.')
            elif stack_status in STACK_WAIT_STATUS:
                LOG.warn('.')
                sleep_timer += 1
            else:
                raise Exception('Stack was in a status I do not recognize', stack_data)


def create_or_update_stack(aws_account, region, ebs_bucket_name):
    """Handle creating or updating the ebs-snapper stack, and waiting"""
    # check for stack, create it if necessary
    stack_name = 'ebs-snapper-{}'.format(aws_account)
    cf_client = boto3.client('cloudformation', region_name=region)

    template_url = "https://s3.amazonaws.com/{}/cloudformation.json".format(ebs_bucket_name)
    try:
        LOG.info('Creating stack from %s', template_url)
        # only required parameter
        DEFAULT_STACK_PARAMS.append({
            'ParameterKey': 'LambdaS3Bucket',
            'ParameterValue': ebs_bucket_name,
            'UsePreviousValue': False})
        response = cf_client.create_stack(
            StackName=stack_name,
            TemplateURL=template_url,
            Parameters=DEFAULT_STACK_PARAMS,
            Capabilities=[
                'CAPABILITY_IAM',
            ])
        LOG.debug(response)
        LOG.warn("Wait while the stack %s is created.", stack_name)
    except ClientError as e:
        if not e.response['Error']['Code'] == 'AlreadyExistsException':
            raise

        try:
            LOG.info('Stack exists, updating stack from %s', template_url)

            # we can't specify "UsePreviousValue" if template didn't have this
            # param before our update. We can only UsePreviousValue if param
            # is already present in previous version of this template.
            sn = stack_name
            sr = cf_client.describe_stacks(StackName=sn)
            es_stack = [x for x in sr.get('Stacks', []) if x['StackName'] == sn]
            es_params = [x.get('Parameters', []) for x in es_stack]
            es_param_keys = [x['ParameterKey'] for x in utils.flatten(es_params)]

            # else we will get the default template value for this param
            params = []
            for k in es_param_keys:
                params.append({'ParameterKey': k, 'UsePreviousValue': True})

            response = cf_client.update_stack(
                StackName=stack_name,
                TemplateURL=template_url,
                Parameters=params,
                Capabilities=[
                    'CAPABILITY_IAM',
                ])
            LOG.debug(response)
            LOG.warn("Waiting while the stack %s is being updated.", stack_name)
        except ClientError as f:
            validation_error = f.response['Error']['Code'] == 'ValidationError'
            no_updates = f.response['Error']['Message'] == 'No updates are to be performed.'
            if not validation_error and not no_updates:
                raise
            LOG.warn('No changes. Stack was not updated.')

    # wait for stack to settle to a completed status
    wait_for_completion(cf_client, stack_name)


def ensure_cloudwatch_logs_retention(aws_account):
    """Be sure retention values are set on CloudWatch Logs for this tool"""
    cwlogs_client = boto3.client('logs', region_name=DEFAULT_REGION)
    loggroup_prefix = '/aws/lambda/ebs-snapper-{}-'.format(str(aws_account))

    list_groups = cwlogs_client.describe_log_groups(logGroupNamePrefix=loggroup_prefix)
    for group in list_groups.get('logGroups', []):
        if group.get('retentionInDays', None):
            LOG.info('Skipping log group %s, as retention is already set', group['logGroupName'])
            continue

        LOG.info('Configuring retention policy on %s log group', group['logGroupName'])
        cwlogs_client.put_retention_policy(
            logGroupName=group['logGroupName'],
            retentionInDays=14
        )


def update_function_and_version(ebs_bucket_name, lambda_zip_filename):
    """Re-publish lambda function and a new version based on our version"""
    lambda_client = boto3.client('lambda', region_name=DEFAULT_REGION)
    lambda_function_list = lambda_client.list_functions()
    lambda_function_map = dict()
    for entry in lambda_function_list['Functions']:
        if 'ebs-snapper' in entry['FunctionName']:
            lambda_function_map[entry['FunctionName']] = entry

    if len(lambda_function_map.keys()) > 0:
        LOG.info("EBS Snapper functions found: %s", lambda_function_map.keys())
    else:
        LOG.warn('No EBS snapshot functions were found.')
        LOG.warn('Please check that EBS snapper stack exists on this account.')

    bytes_read = open(lambda_zip_filename, "rb").read()
    existing_hash = base64.b64encode(hashlib.sha256(bytes_read).digest())

    # publish new version / activate them
    for function_name in lambda_function_map.keys():
        # cleanup opportunity, only retain last 2 versions
        versions_found = []
        version_list = lambda_client.list_versions_by_function(FunctionName=function_name)
        for function_info in version_list['Versions']:
            if function_info['Version'] == '$LATEST':
                continue

            versions_found.append(long(function_info['Version']))

        if len(versions_found) > 2:
            LOG.warn('Found more than 2 old versions of EBS Snapper. Cleaning.')
            try:
                # take off those last 2
                versions_found.sort()
                versions_found.pop()
                versions_found.pop()

                for v in versions_found:
                    LOG.warn('Removing %s function version %s...',
                             function_name,
                             str(v))
                    lambda_client.delete_function(
                        FunctionName=function_name,
                        Qualifier=str(v)
                    )
            except:
                LOG.warn('EBS Snapper cleanup failed!')

        new_hash = lambda_function_map[function_name]['CodeSha256']

        if existing_hash == new_hash:
            LOG.info('Skipping %s, as it is already up to date', function_name)
            continue

        update_response = lambda_client.update_function_code(
            FunctionName=function_name,
            S3Bucket=ebs_bucket_name,
            S3Key=lambda_zip_filename,
            Publish=True
        )
        LOG.info("Updated function code for %s: %s",
                 function_name, update_response['ResponseMetadata'])

        publish_response = lambda_client.publish_version(
            FunctionName=function_name,
            CodeSha256=update_response['CodeSha256'],
            Description=str(ebs_snapper.__version__)
        )
        LOG.info("Published new version for %s: %s",
                 function_name, publish_response['ResponseMetadata'])


def sanity_check(context, installed_region='us-east-1', aws_account_id=None):
    """Retrieve configuration from DynamoDB and return array of dictionary objects"""
    findings = []

    # determine aws account id
    if aws_account_id is None:
        found_owners = utils.get_owner_id(context)
    else:
        found_owners = [aws_account_id]

    if len(found_owners) <= 0:
        findings.append(
            'There are no instances I could find on this account. ' +
            'Cannot figure out the account number without any instances. ' +
            'Without account number, cannot figure out what to name the S3 bucket or stack.'
        )
        return findings
    else:
        aws_account = found_owners[0]

    # The bucket does not exist or you have no access
    bucket_exists = None
    try:
        s3_client = boto3.client('s3', region_name=installed_region)
        ebs_bucket_name = 'ebs-snapper-{}'.format(aws_account)
        s3_client.head_bucket(Bucket=ebs_bucket_name)
        bucket_exists = True
    except ClientError:
        bucket_exists = False

    # Configurations exist but tags do not
    configurations = []
    dynamodb_exists = None
    try:
        configurations = dynamo.list_configurations(context, installed_region)
        dynamodb_exists = True
    except ClientError:
        configurations = []
        dynamodb_exists = False

    # we're going across all regions, but store these in one
    regions = utils.get_regions(must_contain_instances=True)
    ignored_tag_values = ['false', '0', 'no']
    found_config_tag_values = []
    found_backup_tag_values = []

    # check out all the configs in dynamodb
    for config in configurations:
        # if it's missing the match section, ignore it
        if not utils.validate_snapshot_settings(config):
            findings.append(
                "Found a snapshot configuration that isn't valid: {}".format(str(config)))
            continue

        # build a boto3 filter to describe instances with
        configuration_matches = config['match']
        filters = utils.convert_configurations_to_boto_filter(configuration_matches)
        for k, v in configuration_matches.iteritems():

            if str(v).lower() in ignored_tag_values:
                continue

            to_add = '{}, value:{}'.format(k, v)
            found_config_tag_values.append(to_add)

        # if we ended up with no boto3 filters, we bail so we don't snapshot everything
        if len(filters) <= 0:
            LOG.warn('Could not convert configuration match to a filter: %s',
                     configuration_matches)
            findings.append("Found a snapshot configuration that couldn't be converted to a filter")
            continue

        filters.append({'Name': 'instance-state-name',
                        'Values': ['running', 'stopped']})

        found_instances = None
        for r in regions:
            ec2 = boto3.client('ec2', region_name=r)
            instances = ec2.describe_instances(Filters=filters)
            res_list = instances.get('Reservations', [])

            for reservation in res_list:
                inst_list = reservation.get('Instances', [])

                if len(inst_list) > 0:
                    found_instances = True
                    break

            # Look at all the tags on instances
            found_tag_data = ec2.describe_tags(
                Filters=[{'Name': 'resource-type', 'Values': ['instance']}]
            )

            for tag in found_tag_data.get('Tags', []):
                k = tag['Key']
                v = tag['Value']

                if str(v).lower() in ignored_tag_values:
                    continue

                to_add = 'tag:{}, value:{}'.format(k, v)
                if k.lower() in ['backup'] and to_add not in found_backup_tag_values:
                    found_backup_tag_values.append(to_add)

        if not found_instances:
            long_config = []
            for k, v in configuration_matches.iteritems():
                long_config.append('{}, value:{}'.format(k, v))
            findings.append(
                "{} was configured, but didn't match any instances".format(", ".join(long_config)))

    if len(found_backup_tag_values) > 0 or len(found_config_tag_values) > 0:
        if not (bucket_exists and dynamodb_exists):
            findings.append('Configuations or tags are present, but EBS snapper not fully deployed')

    if bucket_exists and dynamodb_exists and len(configurations) == 0:
        findings.append('No configurations existed for this account, but ebs-snapper was deployed')

    # tagged instances without any config
    for s in found_backup_tag_values:
        if s not in found_config_tag_values:
            findings.append('{} was tagged on an instance, but no configuration exists'.format(s))

    LOG.debug("configs: %s", str(found_config_tag_values))
    LOG.debug("tags: %s", str(found_backup_tag_values))

    return findings


def md5sum(fname):
    """Calculate the MD5 sum of a file"""
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()
