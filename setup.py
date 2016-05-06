#!/usr/bin/env python
"""
Setup file for EBS Snapper Lambda V2
"""
from setuptools import setup

setup(
    name='ebs-snapper-lambda-v2-toolbox',
    version='0.1.0',
    description='Project for EC2 volume backups using EBS snapshots',
    author='Rackspace',
    author_email='fps@rackspace.com',
    url='https://github.com/rackerlabs/ebs-snapper-lambda-v2',
    packages=['ebs-snapper-lambda-v2'],
    entry_points={
        'console_scripts': []
    },
)
