# ebs_snapper

This project allows you to schedule regular EBS snapshots and clean up EBS snapshots on EC2. We make use of IAM, Lambda, CloudFormation, DynamoDB, and EC2.

This project is provided under the Apache License, version 2. Pull requests and contributions are always welcome.

- [Requirements](REQUIREMENTS.md)
- [Design](DESIGN.md)
- [Testing](TESTING.md)
- [LICENSE](LICENSE.md)

## Important note

We designed this software as a stopgap for services that aren't storing data in a cloudy, [12 factor way](https://12factor.net/processes): "Twelve-factor processes are stateless and share-nothing. Any data that needs to persist must be stored in a stateful backing service, typically a database." If you're considering implementing this tool in a large environment, it may not work as expected, due to limitations with API rate limiting, snapshot count limits, the settings we provide, etc. We strongly encourage this tool to be used only as a stopgap while an application can be re-written to use S3 and RDS and other durable, AWS-recommended storage mechanisms.

## Releases

[Latest](https://s3.amazonaws.com/production-ebs-snapper/LATEST/ebs_snapper.zip)

## Getting support

This software is provided to you as-is with no warranty or support, under the Apache License v2.0. If you are a [Rackspace Fanatical Support for AWS](http://rackspace.com) customer, and you have additional questions or require additional assistance with this project, please open a support ticket.

## Installing this software on your workstation

NOTE: We recommend [downloading a release from S3](http://s3.amazonaws.com/production-ebs-snapper/), as shown below, into the directory you created above. It should be named `ebs_snapper.zip`. This will help be sure, in addition to using a specific tag for cloning, that you're truly deploying the version you think you are.

Since this package is not currently in PyPi, it will need to be installed locally: git clone the repo (choose a tag, please!) to your workstation then run these commands from inside the repo's main directory:
```
git clone git@github.com:rackerlabs/ebs_snapper.git -b v0.2.0
cd ebs_snapper
wget -O ebs_snapper.zip s3.amazonaws.com/production-ebs-snapper/v0.2.0/ebs_snapper.zip
pip install -r requirements.txt
pip install -e .
```

## Installing the ebs-snapper into an AWS Account

ebs-snapper makes use of the same environment variables of AWS CLI to establish a connection to your AWS account. You'll want to have `AWS_ACCESS_KEY_ID` and your `AWS_SECRET_ACCESS_KEY` (and `AWS_SESSION_TOKEN` if applicable) environment variables set for the appropriate account you'd like to install this software into, and then use the `deploy` command (I highly recommend using `-V` on this command) -- example run, hiding boto output (if you grabbed the zip earlier, you'll also need cloudformation.json and lamba.json from the repository):
```
$ ebs-snapper -V deploy --no_build 2>&1 | grep -v botocore
INFO:ebs_snapper.deploy:Building package using lambda-uploader
INFO:lambda_uploader.package:Building new virtualenv and installing requirements
INFO:lambda_uploader.package:Copying site packages
INFO:lambda_uploader.utils:Copying source files
INFO:lambda_uploader.package:Copying lib64 site packages
INFO:lambda_uploader.utils:Copying source files
INFO:lambda_uploader.package:Copying extra ebs_snapper/lambdas.py into package
INFO:lambda_uploader.utils:Copying source files
INFO:lambda_uploader.package:Creating zipfile
INFO:ebs_snapper.deploy:Creating S3 bucket ebs-snapper-386913580367 if it doesn't exist
INFO:ebs_snapper.deploy:Uploading files into S3 bucket
INFO:ebs_snapper.deploy:Uploading cloudformation.json to bucket ebs-snapper-386913580367
INFO:ebs_snapper.deploy:Uploading ebs_snapper.zip to bucket ebs-snapper-386913580367
INFO:ebs_snapper.deploy:EBS Snapper functions found: [u'ebs-snapper-386913580367-CleanSnapshotFunction-1QJV0HZG6VRAY', u'ebs-snapper-386913580367-FanoutCleanSnapshotFuncti-1A765ZU6QD0AI', u'ebs-snapper-386913580367-FanoutCreateSnapshotFunct-10FU91BLXVZAD', u'ebs-snapper-386913580367-CreateSnapshotFunction-1NE7UCGPK6IS4']
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-386913580367-CleanSnapshotFunction-1QJV0HZG6VRAY: {'HTTPStatusCode': 200, 'RequestId': 'd46a67f6-3e14-11e6-a7ba-1922d5da6516'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-386913580367-CleanSnapshotFunction-1QJV0HZG6VRAY: {'HTTPStatusCode': 201, 'RequestId': 'd56828ee-3e14-11e6-a4be-69a6ba3bb259'}
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-386913580367-FanoutCleanSnapshotFuncti-1A765ZU6QD0AI: {'HTTPStatusCode': 200, 'RequestId': 'd5776b92-3e14-11e6-a79c-b19da9b3c864'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-386913580367-FanoutCleanSnapshotFuncti-1A765ZU6QD0AI: {'HTTPStatusCode': 201, 'RequestId': 'd6c93fb8-3e14-11e6-86c1-c74f9df99951'}
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-386913580367-FanoutCreateSnapshotFunct-10FU91BLXVZAD: {'HTTPStatusCode': 200, 'RequestId': 'd6d881e6-3e14-11e6-a932-f9545c2ef676'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-386913580367-FanoutCreateSnapshotFunct-10FU91BLXVZAD: {'HTTPStatusCode': 201, 'RequestId': 'd7b9e0da-3e14-11e6-8fa4-e3e2a6dc773a'}
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-386913580367-CreateSnapshotFunction-1NE7UCGPK6IS4: {'HTTPStatusCode': 200, 'RequestId': 'd7ca5b9a-3e14-11e6-8c61-c967675510cf'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-386913580367-CreateSnapshotFunction-1NE7UCGPK6IS4: {'HTTPStatusCode': 201, 'RequestId': 'd915c7f2-3e14-11e6-9bdf-896152a8ec90'}
INFO:ebs_snapper.shell:Function shell_deploy completed
```

The first time you run deploy, this will only create the stack in CloudFormation. After the first time, run this again to publish new versions of the tool to an account, as new versions are released.

If you need to manually install this software, you may follow these steps:

1. Create an S3 bucket in "US General" / "us-east-1" and name it `ebs-snapper-<AWS_ACCOUNT_ID>`
1. Run lambda-uploader to build an ebs_snapper.zip file:
```
lambda-uploader --no-upload -r requirements.txt -x ebs_snapper/lambdas.py .
```
1. Upload `cloudformation.json` and `ebs_snapper.zip` to the S3 bucket you created.
1. Create a stack using the [CloudFormation template](cloudformation.json)
1. Publish new versions of the four lambda functions from the template in the previous step. Make sure the description contains only the version of `ebs-snapper` that was uploaded.


## Configuring this software
1. Configuration stanzas live in DynamoDB, and use a compound key `id, aws_account_id`. `id` is a completely arbitrary identifier for each configuration element; `aws_account_id` is the numerical account id that owns EC2 instances in this account.
1. Each compound key `(id, aws_account_id)` in the previous step also owns a configuration stanza made of JSON. The stanza itself is described by the [DESIGN.md](/DESIGN.md) documentation in this repository. Here is an example of one valid configuration (backup everything with a tag named backup that has a value of 'yes'):

```
{
  "match": { "tag:backup": "yes" },
  "snapshot": {
    "retention": "4 days",
    "minimum": 5,
    "frequency": "12 hours"
  },
  "ignore": []
}
```
1. The CLI has a nice method for interacting with these configuration stanzas, but you must still provide them as JSON.

## How to use the CLI

The `ebs-snapper` commandline tool has three subcommands: `snapshot, clean, configure`. For `snapshot` and `clean`, the tool will take any needed snapshots, or clean up any eligible snapshots, respectively, based on the configuration items stored for the AWS account. `configure` is a way for you to interact with the chunks of JSON configuration used by the tool, and has flags for get (`-g / --get`), set (`-s / --set`), delete (`-d / --del`), or list (`-l / --list`). To speed up the configuration subcommand, you can always supply an AWS account ID so that we don't have scan for it, based on EC2 instances and their owners), using (`-a <account id>`).

Additionally, you may be interested in raising the log level of output using `-V` or `-VV`, e.g.: `ebs-snapper -V <rest of command>`. The logging output generally prints AWS connections established to a specific region, as well as parsing and logic information that could be used to debug or look deeper into the tool's behavior.


In the commands below, we enable verbose logging but strip out the boto logging:

### Snapshot command
```
$ ebs-snapper -V snapshot 2>&1 | grep -v boto
INFO:ebs_snapper.snapshot:send_fanout_message: {"instance_id": "i-c40d2659", "region": "us-east-1", "settings": {"snapshot": {"minimum": 5, "frequency": "6 hours", "retention": "5 days"}, "match": {"tag:backup": "yes"}}}
INFO:ebs_snapper.snapshot:send_fanout_message: {"instance_id": "i-e937c975", "region": "us-east-1", "settings": {"snapshot": {"minimum": 5, "frequency": "6 hours", "retention": "5 days"}, "match": {"tag:backup": "yes"}}}
INFO:ebs_snapper.shell:Function shell_fanout_snapshot completed
```

As you can see, the tool has found two instances that match the configuration stanza, and is dispatching the work of evaluating if a snapshot is needed. The determination of whether or not a snapshot is needed is passed on to a second lambda job that will also perform the snapshot API calls if necessary.

### Clean command
```
$ ebs-snapper clean --message '{"region": "us-east-1"}'
Clean up snapshots in region us-east-1
Function shell_clean completed
```

As you can see, the `clean` subcommand does something similar to the snapshot one. It identifies all regions with currently running instances, and then dispatches a lambda job to scan that region for snapshots that might be able to be deleted. The actual work of determining what to delete and performing the delete API calls happens in the other lambda job.

### Configure subcommands

**NOTE** By default, no configurations are created for you. By default, ebs_snapper will do nothing.

List existing configurations stored for this account (will also output the aws_account_id):

```
$ ebs-snapper configure -l
aws_account_id,id
386913580367,tagged_instances
```

Get the extant configuration:

```
$ ebs-snapper configure -g tagged_instances
{"snapshot": {"minimum": 5, "frequency": "6 hours", "retention": "5 days"}, "match": {"tag:backup": "yes"}}
```

Or to make it a bit faster, get the config passing an aws_account_id:
```
$ ebs-snapper configure -g -a 386913580367 tagged_instances
{"snapshot": {"minimum": 5, "frequency": "6 hours", "retention": "5 days"}, "match": {"tag:backup": "yes"}}
```

Now, let's add a second one:
```
$ ebs-snapper configure -s -a 386913580367 daily_tagged '{"snapshot": {"minimum": 5, "frequency": "1 day", "retention": "5 days"}, "match": {"tag:backup": "daily"}}'
Saved to key daily_tagged under account 386913580367
$ ebs-snapper configure -l
aws_account_id,id
386913580367,tagged_instances
386913580367,daily_tagged
```

And finally, let's delete the new one, and list again:
```
$ ebs-snapper configure -d -a 386913580367 daily_tagged
{}
$ ebs-snapper configure -l -a 386913580367
aws_account_id,id
386913580367,tagged_instances
```
