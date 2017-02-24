#!/usr/bin/env python
"""
Setup file for EBS Snapper
"""
from setuptools import setup

setup(
    name='ebs_snapper',
    description='Collection of AWS Lambda functions create, manage, and delete EBS snapshots',
    keywords='aws lambda ebs ec2 snapshot backup',
    version='0.6.0',
    author='Rackspace',
    author_email='fps@rackspace.com',
    url='https://github.com/rackerlabs/ebs_snapper',
    packages=['ebs_snapper'],
    entry_points={
        'console_scripts': [
            'ebs-snapper=ebs_snapper.shell:main'
        ]
    },
    test_suite='tests',
    install_requires=[
        'botocore',
        'boto3',
        'pytimeparse',
        'crontab',
        'lambda_uploader'
    ],
    tests_require=[
        'moto',
        'flake8',
        'pylint',
        'tox',
        'tox-pyenv',
        'pytest',
        'pytest-mock'
    ]
)
