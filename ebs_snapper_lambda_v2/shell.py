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
from ebs_snapper_lambda_v2 import snapshot, clean

LOG = logging.getLogger(__name__)


def main(arv=None):
    """ebs-snapper command line interface."""
    # Check for Python 2.7 (required for Lambda)
    if not (sys.version_info[0] == 2 and sys.version_info[1] == 7):
        raise RuntimeError('ebs-snapper requires Python 2.7')

    parser = argparse.ArgumentParser(
        version=('version %s' % ebs_snapper_lambda_v2.__version__),
        description='Simple way run ebs-snapper lambda jobs')

    verbose = parser.add_mutually_exclusive_group()
    verbose.add_argument('-V', dest='loglevel', action='store_const',
                         const=logging.INFO,
                         help="Set log-level to INFO.")
    verbose.add_argument('-VV', dest='loglevel', action='store_const',
                         const=logging.DEBUG,
                         help="Set log-level to DEBUG.")
    parser.set_defaults(loglevel=logging.WARNING)

    subparsers = parser.add_subparsers(help='sub-command help')

    # fanout sub-commands
    parser_fanout_snapshot = subparsers.add_parser('fanout_snapshot',
                                                   help='Deliver snapshot messages to SNS topic')
    parser_fanout_snapshot.set_defaults(func=shell_fanout_snapshot)
    parser_fanout_clean = subparsers.add_parser('fanout_clean',
                                                help='Deliver cleanup messages to SNS topic')
    parser_fanout_clean.set_defaults(func=shell_fanout_clean)

    # individual sub-commands
    parser_snapshot = subparsers.add_parser('snapshot',
                                            help='execute check/snap logic for a specific instance')
    parser_snapshot.add_argument('-m', '--message')
    parser_snapshot.set_defaults(func=shell_snapshot)
    parser_clean = subparsers.add_parser('clean',
                                         help='execute snapshot cleanup logic for specific region')
    parser_clean.add_argument('-m', '--message')
    parser_clean.set_defaults(func=shell_clean)

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
    snapshot.perform_fanout_all_regions(snapshot.print_fanout_message)
    print('Function shell_fanout_snapshot completed')


def shell_fanout_clean(*args):
    """Print fanout JSON messages, instead of sending them like lambda version."""
    # for every region, send to this function
    clean.perform_fanout_all_regions(clean.print_fanout_message)
    print('Function shell_fanout_clean completed')


def shell_snapshot(*args):
    """Check for snapshots, executing if needed, like lambda version."""
    message_json = json.loads(args[0].message)

    # call the snapshot perform method
    snapshot.perform_snapshot(message_json['region'], message_json['instance_id'])

    print('Function shell_snapshot completed')


def shell_clean(*args):
    """Check for deletable snapshots, executing if needed, like lambda version."""
    message_json = json.loads(args[0].message)

    # call the snapshot cleanup method
    clean.clean_snapshot(message_json['region'])

    print('Function shell_clean completed')
