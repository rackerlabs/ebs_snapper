# -*- coding: utf-8 -*-
# Copyright 2015-2016 Rackspace US, Inc.

"""ebs-snapper - Commandline tool to run lambda jobs for EBS Snapper locally"""

from __future__ import print_function
import logging
import sys
import traceback
import argparse
import json

import ebs_snapper_lambda_v2
from ebs_snapper_lambda_v2 import snapshot, clean, dynamo, utils

LOG = logging.getLogger(__name__)


def main(arv=None):
    """ebs-snapper command line interface."""
    # Check for Python 2.7 (required for Lambda)
    if not (sys.version_info[0] == 2 and sys.version_info[1] == 7):
        raise RuntimeError('ebs-snapper requires Python 2.7')

    parser = argparse.ArgumentParser(
        version=('version %s' % ebs_snapper_lambda_v2.__version__),
        description='Configure, cleanup, or take scheduled EBS volume snapshots')

    verbose = parser.add_mutually_exclusive_group()
    verbose.add_argument('-V', dest='loglevel', action='store_const',
                         const=logging.INFO,
                         help="Set log-level to INFO.")
    verbose.add_argument('-VV', dest='loglevel', action='store_const',
                         const=logging.DEBUG,
                         help="Set log-level to DEBUG.")
    parser.set_defaults(loglevel=logging.WARNING)

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

    # configure subcommand (get, set, delete)
    config_help = '''
        manipulate cleanup and snapshot configuration settings
    '''
    parser_configure = subparsers.add_parser('configure',
                                             help=config_help)
    parser_configure.set_defaults(func=shell_configure)

    # what action for configure?
    action_group = parser_configure.add_mutually_exclusive_group(required=True)
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
    parser_configure.add_argument('-a', '--aws_account_id', nargs='*', default=None)
    parser_configure.add_argument('object_id')
    parser_configure.add_argument('configuration_json', nargs='*', default=None)

    # do all the things!

    try:
        args = parser.parse_args()
        logging.basicConfig(level=args.loglevel)
        args.func(args)
    except Exception:  # pylint: disable=broad-except
        print('Unexpected error. Please report this traceback.', file=sys.stderr)

        traceback.print_exc()
        sys.stderr.flush()
        sys.exit(1)


def shell_fanout_snapshot(*args):
    """Print fanout JSON messages, instead of sending them like lambda version."""
    # for every region and every instance, send to this function
    snapshot.perform_fanout_all_regions()
    LOG.info('Function shell_fanout_snapshot completed')


def shell_fanout_clean(*args):
    """Print fanout JSON messages, instead of sending them like lambda version."""
    # for every region, send to this function
    clean.perform_fanout_all_regions()
    LOG.info('Function shell_fanout_clean completed')


def shell_snapshot(*args):
    """Check for snapshots, executing if needed, like lambda version."""
    message_json = json.loads(args[0].message)

    # call the snapshot perform method
    snapshot.perform_snapshot(
        message_json['region'],
        message_json['instance_id'],
        message_json['settings'])

    LOG.info('Function shell_snapshot completed')


def shell_clean(*args):
    """Check for deletable snapshots, executing if needed, like lambda version."""
    message_json = json.loads(args[0].message)

    # call the snapshot cleanup method
    clean.clean_snapshot(message_json['region'])

    LOG.info('Function shell_clean completed')


def shell_configure(*args):
    """Get, set, or delete configuration in DynamoDB."""

    # lazy retrieve the account id one way or another
    if args[0].aws_account_id is None:
        aws_account_id = utils.get_owner_id()[0]
    else:
        aws_account_id = args[0].aws_account_id[0]

    object_id = args[0].object_id
    action = args[0].conf_action

    if action == 'get':
        LOG.info('Retrieving %s', args[0])
        single_result = dynamo.get_configuration(
            object_id=object_id,
            aws_account_id=aws_account_id)
        if single_result is None:
            print('No configuration found')
        else:
            print(single_result)
    elif action == 'set':
        config = json.loads(args[0].configuration_json[0])
        dynamo.store_configuration(object_id, aws_account_id, config)
        print('Saved {} to key {} under account {}'
              .format(json.dumps(config), object_id, aws_account_id))
    elif action == 'del':
        print(dynamo.delete_configuration(
            object_id=object_id,
            aws_account_id=aws_account_id))
    else:
        # should never get here, from argparse
        raise Exception('invalid parameters', args)

    LOG.info('Function shell_configure completed')
