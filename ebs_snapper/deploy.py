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

import boto3
from lambda_uploader import package as lu_package
from lambda_uploader import config as lu_config

import ebs_snapper
from ebs_snapper import utils

LOG = logging.getLogger(__name__)


def deploy():
    """Main function that does the deploy to an aws account"""
    # lambda-uploader configuration step
    LOG.info("Building package using lambda-uploader")

    lambda_zip_filename = 'lambda_function.zip'
    build_package(lambda_zip_filename)

    # get security credentials from EC2 API
    aws_account = utils.get_owner_id()[0]

    ebs_bucket_name = create_or_update_s3_bucket(aws_account, lambda_zip_filename)

    # check for stack, create it if necessary
    stack_name = 'ebs-snapper-{}'.format(aws_account)
    cf_client = boto3.client('cloudformation')
    stack_list_response = cf_client.list_stacks()
    stack_map = dict()
    for entry in stack_list_response['StackSummaries']:
        stack_map[entry['StackName']] = entry['StackStatus']
    found_ebs_snapper_stack = [x for x in stack_map if stack_name == x]

    if not found_ebs_snapper_stack:
        # create it
        template_url = "https://s3.amazonaws.com/{}/cloudformation.json".format(ebs_bucket_name)
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
        LOG.warn("Exiting while the stack %s is created.", stack_name)
        LOG.warn("Run this later once your stack is ready.")
        return

    # freshen up lambda jobs themselves
    update_function_and_version(ebs_bucket_name, lambda_zip_filename)


def create_or_update_s3_bucket(aws_account, lambda_zip_filename):
    """Ensure the S3 bucket exists, then upload CF and Lambda files"""
    # ensure S3 bucket exists
    s3_client = boto3.client('s3')
    ebs_bucket_name = 'ebs-snapper-{}'.format(aws_account)
    LOG.info("Creating S3 bucket %s if it doesn't exist", ebs_bucket_name)
    s3_client.create_bucket(
        ACL='private',
        Bucket=ebs_bucket_name)

    # upload files to S3 bucket
    LOG.info("Uploading files into S3 bucket")
    upload_files = ['cloudformation.json', lambda_zip_filename]
    for filename in upload_files:
        with open(filename, 'rb') as data:
            LOG.info('Uploading %s to bucket %s', filename, ebs_bucket_name)
            s3_client.put_object(Bucket=ebs_bucket_name, Key=filename, Body=data)

    return ebs_bucket_name


def build_package(lambda_zip_filename):
    """Given this project, package it using lambda_uploader"""
    cfg = lu_config.Config('.', None, role=None)
    pkg = lu_package.Package('.', lambda_zip_filename)
    pkg.clean_zipfile()

    # lambda-uploader step to build zip file
    pkg.extra_file('ebs_snapper/lambdas.py')
    pkg.requirements('requirements.txt')
    pkg.build(cfg.ignore)
    pkg.clean_workspace()


def update_function_and_version(ebs_bucket_name, lambda_zip_filename):
    """Re-publish lambda function and a new version based on our version"""
    lambda_client = boto3.client('lambda')
    lambda_function_list = lambda_client.list_functions()
    lambda_function_map = dict()
    for entry in lambda_function_list['Functions']:
        lambda_function_map[entry['FunctionName']] = entry

    ebs_snapper_functions = [x for x in lambda_function_map.keys() if 'ebs-snapper' in x]
    LOG.info("EBS Snapper functions found: %s", ebs_snapper_functions)

    # publish new version / activate them
    for function_name in ebs_snapper_functions:
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
