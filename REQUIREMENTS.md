# Requirements

## Background

Rackspace has built scheduled EBS snapshot tooling we actively use to provide backup management for customers in production.  As with all our features, they evolve over time and we are planning a series of updates and improvements.  These improvements are currently in the NOW status on our roadmap and are under development.  

## Product guide draft

Rackspace Fanatical Support for AWS provides Aviator service level customers with tooling to help protect Elastic Block Storage (EBS) volume data via volume snapshot management.  EBS snapshots are an effective AWS backup strategy because they balance and solve for multiple aspects of data protection:

-	Full volume backups of root and data devices
-	Efficient storage since EBS snapshots are incremental and only store changed blocks
-	Single file restores are possible by temporarily creating volumes to retrieve point in time files
-	Flexibility to share with other AWS accounts or copy to other AWS regions, for disaster recovery or other such purposes

## Features

-	Snapshotting all EBS volumes on your account at regular intervals
- Ability to select volumes for snapshot by entire ASG, EC2 tags, or instance names
-	EBS volume snapshotting of select volumes, based on configuration settings or defaults
-	Flexible scheduling of snapshots **per instance**, based on configuration settings or defaults
-	Configurable snapshot retention periods of select volumes, based on configuration settings or defaults
-	Ability to retain a minimum number of snapshots regardless of retention period
- All tags from a volume should be transferred to snapshots
-	Rackspace ticket notification and response should an EBS snapshot failure occur

## Out of scope

We discussed the following features, which could be useful, but are currently out of scope:

- Workflow of: Shut down, snapshot, and start up EC2 instance
- File level backups: currently a customer responsibility; not provided by Rackspace.
- Inconsistent snapshots: customers must work with Rackspace to ensure consistent data is written to disk, e.g. local file-level backups of a database server, so that EBS snapshots are consistent and usable.
- Snapshot replication: This tool will not replicate snapshots between regions at this time.
