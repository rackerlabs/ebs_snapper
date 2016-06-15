#!/bin/bash

faws login || exit 1
eval "$(faws -r 979062 env -a 386913580367)"

echo "Building lambda zip file"
rm -rf *.zip
lambda-uploader --no-upload -r requirements.txt -x ebs_snapper/lambdas.py .

echo "Uploading to staging S3 bucket"
FILES="cloudformation.json lambda_function.zip"
for f in $FILES; do
  aws s3 cp $f s3://staging-ebs-snapper-lambda-v2/
done

echo "CF S3 URL: https://s3.amazonaws.com/staging-ebs-snapper-lambda-v2/cloudformation.json"
echo "Bucket name: staging-ebs-snapper-lambda-v2"
