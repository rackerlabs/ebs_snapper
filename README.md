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

## How to use the CLI

The `ebs-snapper` commandline tool has four subcommands: `fanout_snapshot, fanout_clean, snapshot, clean`. For each fanout command, you get a list of JSON messages back. Then use `--message` to pass one of those into the snapshot or clean commands. The shell-based commands don't use SNS, but they do consult the EC2 APIs to find and take snapshots of real instances.

### Fanout snapshot commands
```
$ ebs-snapper fanout_snapshot
send_fanout_message: {"instance_id": "i-c40d2659", "region": "us-east-1"}
send_fanout_message: {"instance_id": "i-b80e2525", "region": "us-east-1"}
Function shell_fanout_snapshot completed
```

### Snapshot for an individual region and instance
```
$ ebs-snapper snapshot --message '{"instance_id": "i-c40d2659", "region": "us-east-1"}'
Perform a snapshot of region us-east-1 on instance i-c40d2659
Function shell_snapshot completed
```

### Fanout cleanup commands
```
$ ebs-snapper fanout_clean
send_fanout_message: {"region": "eu-west-1"}
send_fanout_message: {"region": "ap-southeast-1"}
send_fanout_message: {"region": "ap-southeast-2"}
send_fanout_message: {"region": "eu-central-1"}
send_fanout_message: {"region": "ap-northeast-2"}
send_fanout_message: {"region": "ap-northeast-1"}
send_fanout_message: {"region": "us-east-1"}
send_fanout_message: {"region": "sa-east-1"}
send_fanout_message: {"region": "us-west-1"}
send_fanout_message: {"region": "us-west-2"}
Function shell_fanout_clean completed
```

### Cleanup snapshots in an individual region
```
$ ebs-snapper clean --message '{"region": "us-east-1"}'
Clean up snapshots in region us-east-1
Function shell_clean completed
```
