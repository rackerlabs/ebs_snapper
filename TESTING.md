# Testing

## Overview

We're currently testing using the following tools:

- CI: CircleCI
- Lint: Pylint, Flake8
- Unit: Pytest, AWS CLI

## Lint

We're using pylint and flake8 which are run as part of every CI build, and on every PR. Lint rules are maintained in `.flake8` in the root of the repository.

## Unit testing

It is our goal to test every single method in the modules under the `ebs_snapper` python package. Test sources should always be placed in the `tests/` directory and files named with the pattern `test_<source file being tested>.py`. We intend to have a matching test for for each source file in this package.

For testing functionality that requires stubbed data in AWS, we're using the popular moto framework to mock out boto. For testing functionality that requires more than the API boto provides (e.g. to check that a message was posted to an SNS topic), we're writing extremely thin wrappers in `utils.py` around boto functionality, and then using mocker to confirm the method was called.

## AWS CLI

This is used primarily to validate CloudFormation templates. We run the `cloudformation validate-template` subcommand.
