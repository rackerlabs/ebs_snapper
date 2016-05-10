# ebs-snapper-lambda-v2
Next generation EBS snapshots using Lambda

## See also documentation

- [Requirements](REQUIREMENTS.md)
- [Design](DESIGN.md)
- [Testing](TESTING.md)

## Instructions for using this software

1. Build an archive of this package using [lambda-uploader](http://github.com/rackerlabs/lambda-uploader)
1. Create an S3 bucket and upload the archive to the S3 bucket
1. - OR Alternatively to the steps above, use the [upload.sh](upload.sh) to deploy to S3
1. Create a stack using the [CloudFormation template](cloudformation.json)
