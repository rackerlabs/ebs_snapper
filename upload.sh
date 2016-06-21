#!/bin/bash
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

if [[ -z $FAWS_RACKSPACE_ACCOUNT ]]; then
  export FAWS_RACKSPACE_ACCOUNT=$1
fi
if [[ -z $FAWS_AWS_ACCOUNT ]]; then
  export FAWS_AWS_ACCOUNT=$2
fi

if [[ -z $FAWS_RACKSPACE_ACCOUNT  ]] || [[ -z $FAWS_AWS_ACCOUNT ]]; then
  echo "Usage: ./upload.sh <FAWS_RACKSPACE_ACCOUNT> <FAWS_AWS_ACCOUNT>";
  exit 1
fi

FAWS_CLI_BIN=$(which faws)
if [[ $? -ne 0 ]]; then
  echo "Could not find the faws CLI. Please ensure it's in your path as 'faws'"
  exit 2
fi

FAWS_CLI_BIN=$(which lambda-uploader)
if [[ $? -ne 0 ]]; then
  echo "Could not find the lambda-uploader CLI. Please ensure it's in your path as 'lambda-uploader'"
  exit 2
fi

echo "Ensuring you are authenticated to FAWS"
faws login
if [[ $? -ne 0 ]]; then
  echo "faws-cli login command failed. Try 'faws login' yourself."
  exit 3
fi

echo "Setting environment variables"
FAWS_ENV_OUTPUT=$(faws env)
if [[ $? -ne 0 ]]; then
  echo "faws-cli env command failed. Try 'faws env' yourself."
  exit 4
fi
eval "$FAWS_ENV_OUTPUT"

echo "Creating bucket if it does not exist"
UNIQUE_ID="ebs-snapper-$FAWS_AWS_ACCOUNT"
S3_BUCKET=$UNIQUE_ID
aws s3 mb s3://$S3_BUCKET/

echo "Building lambda zip file"
rm -rf *.zip
lambda-uploader --no-upload -r requirements.txt -x ebs_snapper/lambdas.py .
if [[ $? -ne 0 ]]; then
  echo "lambda-uploader command failed."
  exit 5
fi

echo "Uploading to $S3_BUCKET"
FILES="cloudformation.json lambda_function.zip"
for f in $FILES; do
  aws s3 cp $f s3://$S3_BUCKET/
  if [[ $? -ne 0 ]]; then
    echo "aws s3 command failed on $f."
    exit 6
  fi
done

CF_S3_URL="https://s3.amazonaws.com/$S3_BUCKET/cloudformation.json"
echo "CF S3 URL: $CF_S3_URL"
echo "Bucket name: $S3_BUCKET"

STACK_EXISTS=$(aws cloudformation describe-stacks --stack-name $UNIQUE_ID)
STACK_EXISTS_SUCCESS=$?
if [[ $STACK_EXISTS_SUCCESS -eq 0 ]]; then
  echo "Stack already existed in CloudFormation, not re-creating it."
else
  echo "Stack does not exist in CloudFormation, creating it fresh."
  PARAMS="ParameterKey=LambdaS3Bucket,ParameterValue=$S3_BUCKET,UsePreviousValue=False"
  aws cloudformation create-stack --stack-name $UNIQUE_ID --template-url $CF_S3_URL --parameters $PARAMS --capabilities CAPABILITY_IAM
  if [[ $? -ne 0 ]]; then
    echo "aws cloudformation command failed on $f."
    exit 7
  fi

  echo "Exiting, since the stack may take a while to create."
  echo "Re-run this command later to publish a new version."
fi

VERSION=$(ebs-snapper -v 2>&1 | cut -d " " -f2)
SHA256_SUM=$(sha256sum -b lambda_function.zip | cut -d" " -f1 | xxd -r -p | base64 -w0)
LAMBDA_FUNCTIONS=$(aws lambda list-functions | grep FunctionName | grep ebs-snapper | cut -d ":" -f2 | sed 's/,//g' | xargs echo)

for FUNC in $LAMBDA_FUNCTIONS; do
  echo "Publishing new code for: $FUNC"
  aws lambda update-function-code \
    --s3-bucket $S3_BUCKET \
    --function-name $FUNC \
    --s3-key lambda_function.zip

  if [[ $? -ne 0 ]]; then
    echo "aws lambda update-function-code command failed on $f."
    exit 8
  fi

  echo "Publishing new code version for: $FUNC"
  aws lambda publish-version --function-name $FUNC \
    --code-sha-256 $SHA256_SUM \
    --description $VERSION

  if [[ $? -ne 0 ]]; then
    echo "aws lambda publish-version command failed on $f."
    exit 9
  fi
done

echo "Now, go configure some backups using ebs-snapper's configure subcommand!"
