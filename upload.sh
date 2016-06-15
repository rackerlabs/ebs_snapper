#!/bin/bash

DDI="$1"
AWS_ACCOUNT_ID="$2"
if [[ -z  $DDI  ]] || [[ -z $AWS_ACCOUNT_ID ]]; then
  echo "Usage: ./upload.sh <DDI> <AWS_ACCOUNT_ID>";
  exit
fi

faws login || exit 1
echo "Ensuring you are authenticated to FAWS and setting environment variables"
eval "$(faws -r $DDI env -a $AWS_ACCOUNT_ID)"

echo "Creating bucket if it does not exist"
UNIQUE_ID="ebs-snapper-$AWS_ACCOUNT_ID"
S3_BUCKET=$UNIQUE_ID
aws s3 mb s3://$S3_BUCKET/

echo "Building lambda zip file"
rm -rf *.zip
lambda-uploader --no-upload -r requirements.txt -x ebs_snapper/lambdas.py .

echo "Uploading to $S3_BUCKET"
FILES="cloudformation.json lambda_function.zip"
for f in $FILES; do
  aws s3 cp $f s3://$S3_BUCKET/
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

  echo "Publishing new code version for: $FUNC"
  aws lambda publish-version --function-name $FUNC \
    --code-sha-256 $SHA256_SUM \
    --description $VERSION
done

echo "Now, go configure some backups using ebs-snapper's configure subcommand!"
