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
"""Module for doing EBS snapshots and cleaning up snapshots."""

import logging

__title__ = 'ebs_snapper'
__version__ = '0.6.0'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright Rackspace US, Inc. 2015-2016'
__url__ = 'https://github.com/rackerlabs/ebs-snapper-lambda-v2'

LOG = logging.getLogger()


def timeout_check(context, place):
    """Return True if we have less than 1 minute remaining"""

    remaining = context.get_remaining_time_in_millis()
    if remaining < 60000:  # 1 minute
        LOG.warn('Lambda/Less than 1m remaining in function (%sms): %s',
                 str(remaining),
                 place)
        return True

    return False
