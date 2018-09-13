#!/bin/bash

vercomp () {
    if [[ $1 == $2 ]]
    then
        return 0
    fi
    local IFS=.
    local i ver1=($1) ver2=($2)
    # fill empty fields in ver1 with zeros
    for ((i=${#ver1[@]}; i<${#ver2[@]}; i++))
    do
        ver1[i]=0
    done
    for ((i=0; i<${#ver1[@]}; i++))
    do
        if [[ -z ${ver2[i]} ]]
        then
            # fill empty fields in ver2 with zeros
            ver2[i]=0
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]}))
        then
            return 1
        fi
        if ((10#${ver1[i]} < 10#${ver2[i]}))
        then
            return 2
        fi
    done
    return 0
}

release=$(git describe --always --tags)
sha=$(echo ${CIRCLE_SHA1} | cut -c1-6)
bucket=""
content_type="application/zip"
date=$(date -R)

# create zip file
name=ebs_snapper.zip
ebs-snapper deploy --no_stack --no_upload -a 1234

echo "Moving ${name} to CircleCI artifacts directory"
mv ${name} ${CIRCLE_ARTIFACTS}/${name} || exit 2

if ! [ ${CIRCLE_BRANCH} == "master" ]; then
  echo "Not releasing, this branch is not master"
  exit 0
fi

s3artifact -bucket $AWS_BUCKET -name ${release}/${name} ${CIRCLE_ARTIFACTS}/${name}
s3artifact -bucket $AWS_BUCKET -name LATEST/${name} ${CIRCLE_ARTIFACTS}/${name}

aws_endpoint=https://s3.amazonaws.com/${AWS_BUCKET}
# Check for official release ie v0.5.1 not v0.5.1-kj34kdf
if [[ $release =~ ^v([0-9]+).([0-9]+).([0-9]+)$ ]]; then
  current_version=$(curl -s ${aws_endpoint}/LATEST)
  echo "Latest official release: ${current_version}"

  vercomp $release $current_version
  if [[ $? -eq 0 ]]; then
    echo "Not releasing to S3 because $current_version = $release"
  elif [[ $? -eq 1 ]]; then
    # If the version in S3 is not the latest then update it
    echo "Releasing to S3 because $current_version < $release"
    echo $release > ${CIRCLE_ARTIFACTS}/LATEST
    s3artifact -bucket $AWS_BUCKET -name LATEST -acl public-read ${CIRCLE_ARTIFACTS}/LATEST
  elif [[ $? -eq 2 ]]; then
    echo "Not releasing to S3 because $current_version < $release"
  else
    echo "Something went wrong comparing versions to determine if a release should happen."
    exit 3
  fi
else
  echo "Release $release did not match regex, not going to release"
fi
