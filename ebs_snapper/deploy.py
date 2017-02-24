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
from ebs_snapper import utils

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

        try:
            # check if file in bucket is already there and up to date
            object_summary = s3_client.get_object(Bucket=ebs_bucket_name, Key=filename)
            local_hash = md5sum(filename).strip('"')
            remote_hash = object_summary['ETag'].strip('"')

            LOG.debug("Local file MD5 sum: " + local_hash)
            LOG.debug("ETag from AWS: " + remote_hash)

            if local_hash == remote_hash:
                LOG.info("Skipping upload of %s, already up-to-date in S3", filename)
                continue
        except:
            LOG.info("Failed to checksum local file and remote file, uploading it anyway")

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
    stack_list_response = cf_client.list_stacks()
    stack_summaries = stack_list_response.get('StackSummaries', [])

    stack_map = dict()
    for entry in stack_summaries:
        stack_map[entry['StackName']] = entry['StackStatus']

    template_url = "https://s3.amazonaws.com/{}/cloudformation.json".format(ebs_bucket_name)
    try:
        LOG.info('Creating stack from %s', template_url)
        response = cf_client.create_stack(
            StackName=stack_name,
            TemplateURL=template_url,
            Parameters=[{
                'ParameterKey': 'LambdaS3Bucket',
                'ParameterValue': ebs_bucket_name,
                'UsePreviousValue': False
            }],
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
            response = cf_client.update_stack(
                StackName=stack_name,
                TemplateURL=template_url,
                Parameters=[{
                    'ParameterKey': 'LambdaS3Bucket',
                    'ParameterValue': ebs_bucket_name,
                    'UsePreviousValue': False
                }],
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


def md5sum(fname):
    """Calculate the MD5 sum of a file"""
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()
