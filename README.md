# ebs_snapper

This project allows you to schedule regular EBS snapshots and clean up EBS snapshots on EC2, as well as replicate snapshots to a secondary EC2 region. We make use of IAM, Lambda, CloudFormation, DynamoDB, and EC2.

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

We strongly recommend [using virtualenv](http://docs.python-guide.org/en/latest/dev/virtualenvs/) to install this tool, so you don't have any conflicts between ebs-snapper dependencies and other installed packages or system python packages.

Since this package is not currently in PyPi, it will need to be installed locally: git clone the repo (choose a tag, please!) to your workstation then run these commands from inside the repo's main directory:
```
git clone git@github.com:rackerlabs/ebs_snapper.git -b v0.10.5
cd ebs_snapper
wget -O ebs_snapper.zip s3.amazonaws.com/production-ebs-snapper/v0.10.5/ebs_snapper.zip
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
INFO:ebs_snapper.deploy:Creating S3 bucket ebs-snapper-112233445566 if it doesn't exist
INFO:ebs_snapper.deploy:Uploading files into S3 bucket
INFO:ebs_snapper.deploy:Uploading cloudformation.json to bucket ebs-snapper-112233445566
INFO:ebs_snapper.deploy:Uploading ebs_snapper.zip to bucket ebs-snapper-112233445566
INFO:ebs_snapper.deploy:EBS Snapper functions found: [u'ebs-snapper-112233445566-CleanSnapshotFunction-1QJV0HZG6VRAY', u'ebs-snapper-112233445566-FanoutCleanSnapshotFuncti-1A765ZU6QD0AI', u'ebs-snapper-112233445566-FanoutCreateSnapshotFunct-10FU91BLXVZAD', u'ebs-snapper-112233445566-CreateSnapshotFunction-1NE7UCGPK6IS4']
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-112233445566-CleanSnapshotFunction-1QJV0HZG6VRAY: {'HTTPStatusCode': 200, 'RequestId': 'd46a67f6-3e14-11e6-a7ba-1922d5da6516'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-112233445566-CleanSnapshotFunction-1QJV0HZG6VRAY: {'HTTPStatusCode': 201, 'RequestId': 'd56828ee-3e14-11e6-a4be-69a6ba3bb259'}
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-112233445566-FanoutCleanSnapshotFuncti-1A765ZU6QD0AI: {'HTTPStatusCode': 200, 'RequestId': 'd5776b92-3e14-11e6-a79c-b19da9b3c864'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-112233445566-FanoutCleanSnapshotFuncti-1A765ZU6QD0AI: {'HTTPStatusCode': 201, 'RequestId': 'd6c93fb8-3e14-11e6-86c1-c74f9df99951'}
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-112233445566-FanoutCreateSnapshotFunct-10FU91BLXVZAD: {'HTTPStatusCode': 200, 'RequestId': 'd6d881e6-3e14-11e6-a932-f9545c2ef676'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-112233445566-FanoutCreateSnapshotFunct-10FU91BLXVZAD: {'HTTPStatusCode': 201, 'RequestId': 'd7b9e0da-3e14-11e6-8fa4-e3e2a6dc773a'}
INFO:ebs_snapper.deploy:Updated function code for ebs-snapper-112233445566-CreateSnapshotFunction-1NE7UCGPK6IS4: {'HTTPStatusCode': 200, 'RequestId': 'd7ca5b9a-3e14-11e6-8c61-c967675510cf'}
INFO:ebs_snapper.deploy:Published new version for ebs-snapper-112233445566-CreateSnapshotFunction-1NE7UCGPK6IS4: {'HTTPStatusCode': 201, 'RequestId': 'd915c7f2-3e14-11e6-9bdf-896152a8ec90'}
INFO:ebs_snapper.shell:Function shell_deploy completed
```

The first time you run deploy, this will only create the stack in CloudFormation. After the first time, run this again to publish new versions of the tool to an account, as new versions are released. The resources generated which include the Lambda functions and S3 bucket are generated in the us-east-1 region (N. Virginia) -- even though they talk to, and manage snapshots, in every region. Please see the section below on the `configure` subcommand of the CLI to learn more about configuring this software after installation.

## How to use the CLI

The `ebs-snapper` commandline tool has four subcommands: `snapshot, clean, configure, replication`. For `snapshot` and `clean`, the tool will take any needed snapshots, or clean up any eligible snapshots, respectively, based on the configuration items stored for the AWS account. `replication` is used to trigger replication of snapshots from one region to another. `configure` is a way for you to interact with the chunks of JSON configuration used by the tool, and has flags for get (`-g / --get`), set (`-s / --set`), delete (`-d / --del`), or list (`-l / --list`). To speed up the configuration subcommand, you can always supply an AWS account ID so that we don't have scan for it, based on EC2 instances and their owners), using (`-a <account id>`).

Additionally, you may be interested in raising the log level of output using `-V` or `-VV`, e.g.: `ebs-snapper -V <rest of command>`. The logging output generally prints AWS connections established to a specific region, as well as parsing and logic information that could be used to debug or look deeper into the tool's behavior.


In the commands below, we enable verbose logging but strip out the boto logging:


### Configure subcommands

**IMPORTANT NOTE** By default, no configurations are created for you. By default, ebs_snapper will do nothing. The meaning of every configuration item is described in [DESIGN.md](/DESIGN.md), also in this repository.

#### Background

JSON configuration stanzas live in DynamoDB, and use a compound key `id, aws_account_id`. `id` is a completely arbitrary identifier for each configuration element; `aws_account_id` is the numerical account id that owns EC2 instances in this account. Here is an example of one valid configuration (backup everything with a tag named backup that has a value of 'yes'):

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

#### Examples

### Configure command

List existing configurations stored for this account (will also output the aws_account_id):

```
$ ebs-snapper configure -l
aws_account_id,id
112233445566,tagged_instances
```

Get the extant configuration:

```
$ ebs-snapper configure -g tagged_instances
{"snapshot": {"minimum": 5, "frequency": "6 hours", "retention": "5 days"}, "match": {"tag:backup": "yes"}}
```

Or to make it a bit faster, get the config passing an aws_account_id:
```
$ ebs-snapper configure -g -a 112233445566 tagged_instances
{"snapshot": {"minimum": 5, "frequency": "6 hours", "retention": "5 days"}, "match": {"tag:backup": "yes"}}
```

Now, let's add a second one:
```
$ ebs-snapper configure -s -a 112233445566 daily_tagged '{"snapshot": {"minimum": 5, "frequency": "1 day", "retention": "5 days"}, "match": {"tag:backup": "daily"}}'
Saved to key daily_tagged under account 112233445566
$ ebs-snapper configure -l
aws_account_id,id
112233445566,tagged_instances
112233445566,daily_tagged
```

And finally, let's delete the new one, and list again:
```
$ ebs-snapper configure -d -a 112233445566 daily_tagged
{}
$ ebs-snapper configure -l -a 112233445566
aws_account_id,id
112233445566,tagged_instances
```

We also provide an easy way to sanity check configurations:
```
$ ebs-snapper configure -c -a 112233445566
112233445566: No configurations existed for this account, but ebs-snapper was deployed
112233445566: tag:Backup, value:5 was configured, but didn't match any instances
112233445566: tag:Backup, value:30 was configured, but didn't match any instances
112233445566: tag:Backup, value:10 was configured, but didn't match any instances
```

### Snapshot command
```
$ ebs-snapper -V snapshot
INFO:root:Reviewing snapshots in region us-east-1
INFO:root:Building cache of instance, volume, and snapshots in us-east-1
INFO:root:This may take a while...
INFO:root:No configurations found in us-east-1, not building cache
INFO:root:Reviewing snapshots in region us-west-2
INFO:root:Building cache of instance, volume, and snapshots in us-west-2
INFO:root:This may take a while...
INFO:root:No configurations found in us-west-2, not building cache
INFO:root:Function shell_fanout_snapshot completed
```

As you can see, the tool has found two instances that match the configuration stanza, and is dispatching the work of evaluating if a snapshot is needed. The determination of whether or not a snapshot is needed is passed on to a second lambda job that will also perform the snapshot API calls if necessary, however when run interactively using the CLI, all of the logic happens directly on the client (no Lambda jobs run).

### Clean command
```
ebs-snapper -V clean
INFO:root:clean_snapshot in region us-east-1
INFO:root:Building cache of instance, volume, and snapshots in us-east-1
INFO:root:This may take a while...
INFO:root:Retrieved 1 DynamoDB configurations for caching
INFO:root:Retrieved 1 instances for caching
INFO:root:Retrieved 1 volumes for caching
INFO:root:Retrieved 10 snapshots for caching
WARNING:root:Deleting snapshot snap-0de3326777957aa1d from us-east-1 (2017-03-05, count=10 > 5)
INFO:root:Function clean_snapshots_tagged completed, deleted count: 1
INFO:root:Function clean_snapshot completed
INFO:root:Function clean_send_fanout_message completed
INFO:root:clean_snapshot in region us-west-1
INFO:root:Building cache of instance, volume, and snapshots in us-west-1
INFO:root:This may take a while...
INFO:root:Retrieved 1 DynamoDB configurations for caching
INFO:root:Retrieved 0 instances for caching
INFO:root:Retrieved 0 volumes for caching
INFO:root:Retrieved 0 snapshots for caching
WARNING:root:No snapshots were cleaned up for the entire region us-west-1
INFO:root:Function clean_snapshot completed
INFO:root:Function clean_send_fanout_message completed
INFO:root:Function clean_perform_fanout_all_regions completed
INFO:root:Function shell_fanout_clean completed
```

As you can see, the `clean` subcommand does something similar to the snapshot one. It identifies all regions with currently running instances, and then dispatches a lambda job to scan that region for snapshots that might be able to be deleted. The actual work of determining what to delete and performing the delete API calls happens in the other lambda job, however when run interactively using the CLI, all of the logic happens directly on the client (no Lambda jobs run).

Specifically for the clean job, a cache is built of much of the needed data to do cleanup, since it's much more efficient to fetch in bulk than to fetch over and over for every single snapshot (and causes less calculations to be repeated).

### Replication command
```
ebs-snapper -V replication
INFO:root:Performing snapshot replication in region us-east-1
INFO:root:Working on copying this snapshot snap-0daf235945e307e7c (if needed): Created from i-05d0486d6c8b1ae49 by EbsSnapper(0.10.5) for ami-c7c546d1 from vol-0d4be5bde49115a56
INFO:root:Not creating more snapshots, since snapshot_id snap-0daf235945e307e7c was already found in us-west-2
INFO:root:Working on copying this snapshot snap-08123b99992aba69d (if needed): Created from i-088e9520113fb4e35 by EbsSnapper(0.10.5) for ami-7250d264 from vol-0217da8a108684fa4
INFO:root:Not creating more snapshots, since snapshot_id snap-08123b99992aba69d was already found in us-west-2
INFO:root:Working on copying this snapshot snap-08bb5aff7b2ccef49 (if needed): Created from i-05b64394cd94260f4 by EbsSnapper(0.10.5) for ami-7250d264 from vol-0349099862e322830
INFO:root:Not creating more snapshots, since snapshot_id snap-08bb5aff7b2ccef49 was already found in us-west-2
INFO:root:Working on copying this snapshot snap-06476a1fdf283c0e0 (if needed): Created from i-05b64394cd94260f4 by EbsSnapper(0.10.5) for ami-7250d264 from vol-029e224bfe6c74001
INFO:root:Not creating more snapshots, since snapshot_id snap-0e30eba44dc55832e was already found in us-west-2
WARNING:root:Lambda/Less than 1m remaining in function (59725ms): perform_replication
INFO:root:Performing snapshot replication in region us-west-1
WARNING:root:Lambda/Less than 1m remaining in function (50984ms): perform_replication
WARNING:root:Lambda/Less than 1m remaining in function (49823ms): perform_replication
INFO:root:Performing snapshot replication in region us-west-2
WARNING:root:Lambda/Less than 1m remaining in function (0ms): perform_replication
WARNING:root:Lambda/Less than 1m remaining in function (0ms): perform_replication
INFO:root:Function shell_fanout_snapshot_replication completed
```

Note that replication is scheduled using CloudWatch events by the snapshot job to enable or disable a separate replication event, and relies on special tags as described in [DESIGN.md](/DESIGN.md) in the "Replication" section.
