#!/usr/bin/env python
"""
Setup file for EBS Snapper
"""
from setuptools import setup

setup(
    name='ebs_snapper',
    version='0.1.0',
    description='Project for EC2 volume backups using EBS snapshots',
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
        'pytimeparse'
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
