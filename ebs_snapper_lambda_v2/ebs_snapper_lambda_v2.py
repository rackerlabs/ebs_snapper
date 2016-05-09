import boto3
import json


def get_regions():
    client = boto3.client('ec2')
    regions = client.describe_regions()
    region_names = []
    for region in regions['Regions']:
        region_names.append(region['RegionName'])
    return region_names


def get_topic_arn(topic_name):
    regions = get_regions()
    for region in regions:
        client = boto3.client('sns', region_name=region)
        topics = client.list_topics()
        for topic in topics['Topics']:
            splits = topic['TopicArn'].split(':')
            if splits[5] == topic_name:
                return topic['TopicArn']
    raise Exception('Could not find an SNS topic {}'.format(topic_name))


def lambda_ebs_snapper_fanout_snap(event, context):
    sns_client = boto3.client('sns')
    sns_topic = get_topic_arn('CreateSnapshotTopic')

    message_object = {'test': True}
    message_string = json.dumps(message_object)

    # push a dummy message to the topic, to make sure it works
    sns_client.publish(TopicArn=sns_topic, Message=message_string)

    print('Function lambda_ebs_snapper_fanout_snap completed')


def lambda_ebs_snapper_fanout_clean(event, context):
    sns_client = boto3.client('sns')
    sns_topic = get_topic_arn('CleanSnapshotTopic')

    message_object = {'test': True}
    message_string = json.dumps(message_object)

    # push a dummy message to the topic, to make sure it works
    sns_client.publish(TopicArn=sns_topic, Message=message_string)

    print('Function lambda_ebs_snapper_fanout_clean completed')


def lambda_ebs_snapper_snap(event, context):
    records = event.get('Records')
    for record in records:
        sns = record.get('Sns')
        if sns is None:
            continue
        message = sns.get('Message')
        message_json = json.loads(message)
        str(message_json)
    print('Function lambda_ebs_snapper_snap completed')


def lambda_ebs_snapper_clean(event, context):
    records = event.get('Records')
    for record in records:
        sns = record.get('Sns')
        if sns is None:
            continue
        message = sns.get('Message')
        message_json = json.loads(message)
        str(message_json)
    print('Function lambda_ebs_snapper_clean completed')
