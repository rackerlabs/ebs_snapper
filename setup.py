#!/usr/bin/env python
"""
Setup file for EBS Snapper Lambda V2
"""
from setuptools import setup

setup(
    name='ebs_snapper_lambda_v2',
    version='0.1.0',
    description='Project for EC2 volume backups using EBS snapshots',
    author='Rackspace',
    author_email='fps@rackspace.com',
    url='https://github.com/rackerlabs/ebs_snapper_lambda_v2',
    packages=['ebs_snapper_lambda_v2'],
    entry_points={
        'console_scripts': [
            'ebs-snapper=ebs_snapper_lambda_v2.shell:main'
        ]
    },
    test_suite='tests',
    install_requires=[
        'botocore',
        'boto3',
        'logging'
    ],
    tests_require=[
        'moto',
        'flake8',
        'pylint',
        'tox',
        'tox-pyenv',
        'pytest'
    ]
)
