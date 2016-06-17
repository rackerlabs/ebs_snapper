# ebs_snapper

This project allows you to schedule regular EBS snapshots and clean up EBS snapshots on EC2. We make use of IAM, Lambda, CloudFormation, DynamoDB, and EC2.

This project is provided under the Apache License, version 2. Pull requests and contributions are always welcome.

- [Requirements](REQUIREMENTS.md)
- [Design](DESIGN.md)
- [Testing](TESTING.md)
- [LICENSE](LICENSE.md)

## Getting support

This software is provided to you with no warranty beyond the Apache License v2.0. If you are a [Rackspace](http://rackspace.com) customer, and you have additional questions or require additional assistance with this project, please open a support ticket.

## Installing this software

This software comes with a script [upload.sh](/upload.sh), that performs the following steps. If you need to manually install this software, you may follow these steps or read along in `upload.sh`.

1. Create an S3 bucket in "US General" / "us-east-1" and name it `ebs-snapper-<FAWS_ACCOUNT_ID>`
1. Run lambda-uploader to build a lambda_function.zip file:
```
lambda-uploader --no-upload -r requirements.txt -x ebs_snapper/lambdas.py .
```
1. Upload `cloudformation.json` and `lambda_function.zip` to the S3 bucket you created.
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
  }
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
