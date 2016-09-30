# Changelog

## 0.3.3

- Work to reduce alarms to more reasonable levels (#88)
- Clarify that no configs are created (#87)

## 0.3.2

- Be sure SNS methods take region arg (#86)
- Check for SNS message inputs (#84)

## 0.3.1

- Swallow errors on delete of a snapshot if the snapshot is in use by an AMI (#82)

## 0.3.0

- Add the ability to clean up snapshots iteratively (#79)
- Add timing measurements on cleanup (#66)
- Update docs to reflect not building it locally (#73)
- Don't copy `aws:` tags (#78)
- Bump to lambda-uploader's latest release (#53)
- Allow broader tags (#67)
- Add description to snapshots created (#74)
- Make deployments significantly faster for S3 (#71)
- Don't require lambda.json (#70)
- Don't error if invoked from console (#68)

## 0.2.0

- Introduce crontab syntax for backups (#62)
- Correct pylint testing to run correctly (#63)
- Add script to release/CD successful tagged builds to S3 (#50)
- Add flags to disable uploading, building, and stack updating to deploy command
- Add deploy command for deploying to new accounts (#58)
- Tweak thresholds for alerting (#57)

## 0.1.0

- Initial release. See [REQUIREMENTS.md](REQUIREMENTS.md) and [DESIGN.md](DESIGN.md) for initial design and requirements.
