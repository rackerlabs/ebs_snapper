#!/bin/bash

faws login || exit 1
eval "$(faws -r 979062 env -a 386913580367)"

sh upload.sh

VERSION=$(ebs-snapper -v 2>&1 | cut -d " " -f2)
SHA256_SUM=$(sha256sum -b lambda_function.zip | cut -d" " -f1 | xxd -r -p | base64 -w0)
LAMBDA_FUNCTIONS=$(aws lambda list-functions | grep FunctionName | grep ebs-snapper-lambda | cut -d ":" -f2 | sed 's/,//g' | xargs echo)

for FUNC in $LAMBDA_FUNCTIONS; do
  echo "Publishing new code for: $FUNC"
  aws lambda update-function-code \
    --s3-bucket staging-ebs-snapper-lambda-v2 \
    --function-name $FUNC \
    --s3-key lambda_function.zip

  echo "Publishing new code version for: $FUNC"
  aws lambda publish-version --function-name $FUNC \
    --code-sha-256 $SHA256_SUM \
    --description $VERSION
done
