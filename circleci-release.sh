#!/bin/bash

if ! [ ${CIRCLE_BRANCH} == "master" ]; then
  echo "Not releasing, this branch is not master"
  exit 0
fi

release=$(git describe --always --tags)
sha=$(echo ${CIRCLE_SHA1} | cut -c1-6)
bucket=""
content_type="application/zip"
date=$(date -R)

name=ebs_snapper.zip
ebs-snapper deploy --no_stack --no_upload -a 1234 && mv ${name} ${CIRCLE_ARTIFACTS}/${name}
s3artifact -bucket $AWS_BUCKET -name ${release}/${name} ${CIRCLE_ARTIFACTS}/${name}
s3artifact -bucket $AWS_BUCKET -name latest/${name} ${CIRCLE_ARTIFACTS}/${name}

aws_endpoint=https://s3.amazonaws.com/${AWS_BUCKET}
# Check for official release ie v0.5.1 not v0.5.1-kj34kdf
if [[ $release =~ ^v([0-9]+).([0-9]+).([0-9]+)$ ]]; then

  current_version=$(curl -s ${aws_endpoint}/LATEST)
  # If the version in S3 is not the latest then update it
  if [[ $current_version < $release ]]; then
    echo "Releasing to S3 because $current_version < $release"
    echo $release > ${CIRCLE_ARTIFACTS}/LATEST
    s3artifact -bucket $AWS_BUCKET -name LATEST -acl public-read ${CIRCLE_ARTIFACTS}/LATEST
  else
    echo "Not releasing to S3 because $current_version >= $release"
  fi
else
  echo "Release $release did not match regex, not going to release"
fi
