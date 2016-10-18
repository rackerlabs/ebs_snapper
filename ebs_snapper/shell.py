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
"""ebs-snapper - Commandline tool to run lambda jobs for EBS Snapper locally"""

from __future__ import print_function
import logging
import sys
import traceback
import argparse
import json

import ebs_snapper
from ebs_snapper import snapshot, clean, dynamo, utils, deploy

LOG = logging.getLogger()
CTX = utils.MockContext()


def main(arv=None):
    """ebs-snapper command line interface."""
    # Check for Python 2.7 (required for Lambda)
    if not (sys.version_info[0] == 2 and sys.version_info[1] == 7):
        raise RuntimeError('ebs-snapper requires Python 2.7')

    # allow 15m for the cli, instead of lambda's 5
    CTX.set_remaining_time_in_millis(60000*15)

    parser = argparse.ArgumentParser(
        version=('version %s' % ebs_snapper.__version__),
        description='Configure, cleanup, or take scheduled EBS volume snapshots')

    verbose = parser.add_mutually_exclusive_group()
    verbose.add_argument('-V', dest='loglevel', action='store_const',
                         const=logging.INFO,
                         help="Set log-level to INFO.")
    verbose.add_argument('-VV', dest='loglevel', action='store_const',
                         const=logging.DEBUG,
                         help="Set log-level to DEBUG.")
    parser.set_defaults(loglevel=logging.WARNING)

    # region setting
    parser.add_argument('-t', '--tool_region', dest='conf_toolregion',
                        nargs='?', default='us-east-1',
                        help="dynamodb & SNS region used by ebs-snapper (us-east-1 is default)")

    # Sub-commands & help
    subparsers = parser.add_subparsers(help='sub-command help')

    # snapshot subcommand (fanout)
    snapshot_help = '''
        execute snapshots for one or more EBS volumes (if due)
    '''
    parser_snapshot = subparsers.add_parser('snapshot', help=snapshot_help)
    parser_snapshot.set_defaults(func=shell_fanout_snapshot)

    # clean subcommand (fanout)
    clean_help = '''
        clean up one or more EBS snapshots (if due)
    '''
    parser_clean = subparsers.add_parser('clean', help=clean_help)
    parser_clean.set_defaults(func=shell_fanout_clean)

    # deploy subcommand
    deploy_help = '''
        deploy this tool (or update to a new version) on the account
    '''
    parser_deploy = subparsers.add_parser('deploy', help=deploy_help)
    parser_deploy.add_argument('-a', '--aws_account_id', nargs='?', default=None)
    parser_deploy.add_argument('-n', '--no_build', dest='no_build',
                               action='store_const', const=True, default=False)
    parser_deploy.add_argument('-m', '--no_upload', dest='no_upload',
                               action='store_const', const=True, default=False)
    parser_deploy.add_argument('-o', '--no_stack', dest='no_stack',
                               action='store_const', const=True, default=False)
    parser_deploy.set_defaults(func=shell_deploy)

    # configure subcommand (get, set, delete)
    config_help = '''
        manipulate cleanup and snapshot configuration settings
    '''
    parser_configure = subparsers.add_parser('configure',
                                             help=config_help)
    parser_configure.set_defaults(func=shell_configure)

    # what action for configure?
    action_group = parser_configure.add_mutually_exclusive_group(required=True)
    action_group.add_argument('-l', '--list', dest='conf_action', action='store_const',
                              const='list',
                              help="List configuration items")
    action_group.add_argument('-g', '--get', dest='conf_action', action='store_const',
                              const='get',
                              help="Get configuration item")
    action_group.add_argument('-s', '--set', dest='conf_action', action='store_const',
                              const='set',
                              help="Set configuration item")
    action_group.add_argument('-d', '--delete', dest='conf_action', action='store_const',
                              const='del',
                              help="Delete configuration item")
    action_group.set_defaults(conf_action=None)

    # configure parameters
    parser_configure.add_argument('-a', '--aws_account_id', nargs='?', default=None)
    parser_configure.add_argument('object_id', nargs='?', default=None)
    parser_configure.add_argument('configuration_json', nargs='?', default=None)

    # do all the things!
    try:
        args = parser.parse_args()

        # make sure boto stays quiet
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('boto3').setLevel(logging.WARNING)

        logging.basicConfig(level=args.loglevel)
        LOG.setLevel(args.loglevel)

        args.func(args)
    except Exception:  # pylint: disable=broad-except
        print('Unexpected error. Please report this traceback.', file=sys.stderr)

        traceback.print_exc()
        sys.stderr.flush()
        sys.exit(1)


def shell_fanout_snapshot(*args):
    """Print fanout JSON messages, instead of sending them like lambda version."""
    # for every region and every instance, send to this function
    snapshot.perform_fanout_all_regions(CTX, cli=True)
    LOG.info('Function shell_fanout_snapshot completed')


def shell_fanout_clean(*args):
    """Print fanout JSON messages, instead of sending them like lambda version."""
    # for every region, send to this function
    clean.perform_fanout_all_regions(CTX, cli=True)
    LOG.info('Function shell_fanout_clean completed')


def shell_deploy(*args):
    """Deploy this tool to a given account."""
    # call the snapshot cleanup method
    deploy.deploy(
        CTX,
        aws_account_id=args[0].aws_account_id,
        no_build=args[0].no_build,
        no_upload=args[0].no_upload,
        no_stack=args[0].no_stack
        )

    LOG.info('Function shell_deploy completed')


def shell_configure(*args):
    """Get, set, or delete configuration in DynamoDB."""

    # lazy retrieve the account id one way or another
    if args[0].aws_account_id is None:
        aws_account_id = utils.get_owner_id(CTX)[0]
    else:
        aws_account_id = args[0].aws_account_id
    LOG.debug("Account: %s", aws_account_id)

    object_id = args[0].object_id
    action = args[0].conf_action
    installed_region = args[0].conf_toolregion

    if action == 'list':
        LOG.info('Listing all object keys')
        list_results = dynamo.list_ids(
            CTX,
            installed_region,
            aws_account_id=aws_account_id)
        if list_results is None or len(list_results) == 0:
            print('No configurations found')
        else:
            print("aws_account_id,id")
            for r in list_results:
                print("{},{}".format(aws_account_id, r))
    elif action == 'get':
        if object_id is None:
            raise Exception('must provide an object key id')
        else:
            LOG.debug("Object key: %s", object_id)

        LOG.info('Retrieving %s', args[0])

        single_result = dynamo.get_configuration(
            CTX,
            installed_region,
            object_id=object_id,
            aws_account_id=aws_account_id)
        if single_result is None:
            print('No configuration found')
        else:
            print(json.dumps(single_result))
    elif action == 'set':
        if object_id is None:
            raise Exception('must provide an object key id')
        else:
            LOG.debug("Object key: %s", object_id)

        config = json.loads(args[0].configuration_json)
        LOG.debug("Configuration: %s", config)
        dynamo.store_configuration(installed_region, object_id, aws_account_id, config)
        print('Saved to key {} under account {}'
              .format(object_id, aws_account_id))
    elif action == 'del':
        print(dynamo.delete_configuration(
            installed_region,
            object_id=object_id,
            aws_account_id=aws_account_id))
    else:
        # should never get here, from argparse
        raise Exception('invalid parameters', args)

    LOG.info('Function shell_configure completed')
