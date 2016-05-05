# Design of EBS Snapper

## Background & Technologies

We're going to use AWS Lambda jobs for each of the regularly scheduled tasks that the ebs snapper performs. There will be one job as well as one Lambda job simply to fan out / parallelize doing snapshots for each region that we're interested in. Even though we will be running snapshots for volumes in all regions, the lambda jobs will all be running in us-east-1 for now. Each customer would have a separate install of this lambda job; we will not share the Lambda job across multiple customers.

## Data storage, state information

There are one main data storage location for this project: DynamoDB to store the configuration data below. There is one exception -- tags on EC2 volume snapshots will be used to store only the expiration date of the snapshot itself. We chose to store the expiration date of a snapshot as a tag on the snapshot because it's essentially metadata about that snapshot. All other configuration data isn't snapshot specific, and might not even be instance-specific; we expect many customers will have an empty configuration (no snapshots anywhere) or a small configuration stanza (to match just a small number of instances)

- Configuration elements:

  - Matching elements (multiple elements are AND'd together by AWS describe* APIs):
    - Instance ID
    - Tag on Instance
    - ASG ID for membership
    - Name of Instance

  - Settings for each match + allowed values
    - Retention of snapshots (R days, weeks)
    - Minimum number of snapshots (M, integer, defaults to 1)
    - Frequency of snapshots (F hours, days, weeks, minimum is 1 hour)

## Actual algorithms/lambda jobs

### Fan Out 1 - 'ebs_snapper_fanout_snap'

This algorithm is pretty straightforward. We need to fan out per region, and then trigger the snapshot lambda job for each region. This job will run hourly to trigger the snapshot.

### Fan Out 2 - 'ebs_snapper_fanout_clean'

This algorithm is pretty straightforward. We need to fan out per region, and then trigger the cleanup lambda jobs for each region. This job will run daily to trigger the cleanup.

### Snapshot algorithm - 'ebs_snapper_snap'

For the input region, loop through every configuration stanze, and search for EC2 instances that match. If no matching elements are given, a search will return all ec2 instances and queue all instances up using the settings provided. Determine the most recent snapshot taken of any volume. If there are volumes without a snapshot or volumes with a snapshot "StartTime" older than the minimum frequency of snapshots, issue a snapshot of all volumes. Tag the snapshot with the calculated value of (now+retention duration). This job will run on SNS trigger from the fanout job.

### Clean up algorithm - 'ebs_snapper_clean'

For the input region, loop through every snapshot (ec2-describe-snapshots) with a retention tag. If the current time is after the retention value, and there are a minimum number of snapshots present, delete the snapshot. This job runs daily.

## Python modules, project organization

For now, this is all going to be in one Python module, plus a 2nd module that contains only the Lambda functions. We'll use Lambda Uploader and specify a different function as the entry point for each lambda job above. We'll also produce a CloudFormation template that creates:
  - SNS topic for fanout
  - S3 bucket for lambda job source code
  - Lambda execution role (including needed permissions)
  - Cloud watch alarms for job errors (failed snapshots and failed deletion of snapshots)
  - Schedules for the Lambda jobs using CloudWatch events
