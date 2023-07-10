import click
from cli import pass_context

#-{Import unique to this command}--------------------------------------------------------------------------------------#
import sys
import boto3
import botocore
import os
from time import sleep
import configparser
import re
import json

#-{Command Function/Classes}-------------------------------------------------------------------------------------------#


def get_name_from_description(description, matched_desc_patterns = ['i-', 'ami-', 'vol-']):
    """
    Used to turn a description into a possible name format, was designed to be used for snapshots.
    Currently not implemented as we are skipping snapshots that don't have a volume to pull data from for now.
    Functionality kept in case we need to enable it down the line.

    :param description: (String) A description.
    :param matched_desc_patterns: (List) Patterns to match for naming against.
    :return:
    """
    pattern = re.compile('(?i)\\b[a-z]+-[a-z0-9]+')

    # try to parse the description for information that is useful.
    name_values = []
    for match in pattern.findall(description):
        for match_pattern in matched_desc_patterns:
            if match.startswith(match_pattern):
                name_values.append(match)

    # fallback to a best attempt with a normalized description.
    if not name_values:
        name_values.append(re.sub('[\W_]+', ' ', description, flags=re.UNICODE).replace(' ', '-').lower()[0:24])

    return '_'.join(name_values)


def get_rds_instance_tags(context, region):
    log_prefix = 'get_rds_instance_tags'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    instance_tags   = {}
    instances       = context.get_from_aws_api(
        api_namespace='rds', api_name='describe_db_instances', api_response_key='DBInstances',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxRecords': 99999}}, region=region
    )

    for instance in instances:
        instance_tags[instance['DBInstanceIdentifier']] = instance['TagList']

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return instance_tags


def get_rds_cluster_tags(context, region):
    log_prefix = 'get_rds_instance_tags'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    instance_tags   = {}
    instances       = context.get_from_aws_api(
        api_namespace='rds', api_name='describe_db_clusters', api_response_key='DBClusters',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxRecords': 99999}}, region=region
    )

    for instance in instances:
        instance_tags[instance['DBClusterIdentifier']] = instance['TagList']

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return instance_tags


def get_ec2_tags(context, region, resource_types = ['instance']):
    """
    Leveraging the EC2 DescribeTags api to compile a dict of matching resources that have been tagged.
    :param context: (Object) Clicks Instance
    :param region: (String) name of the AWS region.
    :param resource_types: (List) resource types to look up, the api allows for one or more.
    :return: Dict with a key of the ResourceId and all tags associated.
    """
    log_prefix = 'get_ec2_tags'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    instances       = {}
    instance_tags   = context.get_from_aws_api(
        api_namespace='ec2', api_name='describe_tags', api_response_key='Tags', api_cache_ttl=1,
        api_request_config={
            'Filters': [{'Name': 'resource-type', 'Values': resource_types}],
            'PaginationConfig': {'MaxRecords': 99999}
        },
        region=region
    )

    for instance_tag in instance_tags:
        if instance_tag['ResourceId'] in instances:
            tags = instances[instance_tag['ResourceId']]
        else:
            tags = []
        tags.append({'Key': instance_tag['Key'], 'Value': instance_tag['Value']})
        instances[instance_tag['ResourceId']] = tags

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return instances


def debug_exit(o):
    debug_output(o)
    sys.exit()


def debug_output(o):
    print(json.dumps(o, indent=4, sort_keys=True, default=str))


def get_by_key_match(items, key, value, return_key = None, default = None):
    """
    Used to iterate over items and look for a matching key/value; optionally return a subset of that match.
    name_tag = get_by_key_match(existing_tags, 'Key', 'Name', 'Value')
    :param items: (List) Containing dictionaries
    :param key: (String) Match this key in each dict.
    :param value: (String) Match this value to the value found in a dict Key.
    :param return_key: (String) If set, return a subset of the matched dict.
    :param default: If no match, this value is returned.
    :return:
    """
    for item in items:
        if item[key] == value:
            if return_key:
                if return_key in item:
                    return item[return_key]
                else:
                    return default
            else:
                return item
    return default


def get_resource_arn(resource_id, region, account_id):
    """
    Validates the arn format, if the id passed can be generated manually, we'll try that before failing.
    Some api's do not return an arn for the resource, which is just so AWS; now we have this to maintain for them.
    Documentation on arn formats: https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html
    :param resource_id:
    :param region:
    :param account_id:
    :return:
    """
    if resource_id.startswith('arn:'):
        return resource_id

    if resource_id.startswith('vol-'):
        return 'arn:aws:ec2:{}:{}:volume/{}'.format(region, account_id, resource_id)

    if resource_id.startswith('snap-'):
        return 'arn:aws:ec2:{}:{}:snapshot/{}'.format(region, account_id, resource_id)

    if resource_id.startswith('i-'):
        return 'arn:aws:ec2:{}:{}:instance/{}'.format(region, account_id, resource_id)

    if resource_id.startswith('elb-'):
        return 'arn:aws:elasticloadbalancing:{}:{}:loadbalancer/{}'.format(region, account_id, resource_id.replace('elb-', ''))

    if resource_id.startswith('s3-'):
        return 'arn:aws:s3:::{}'.format(resource_id.replace('s3-', ''))

    if resource_id.startswith('redshift-'):
        return 'arn:aws:redshift:{}:{}:cluster:{}'.format(region, account_id, resource_id.replace('redshift-', ''))

    raise Exception('Invalid ARN format passed, could not generate it::[{}]'.format(resource_id))


def tag_resources(context, resources, region):
    """
    This functionality leverages the general AWS Resource Group Tagging API; as such only some resource types are supported.
    We are trying to validate the resource by the id passed, but it doesn't mean it's supported.
    Supported resources: https://docs.aws.amazon.com/ARG/latest/userguide/supported-resources.html
    :param context:
    :param resources:
    :param region:
    :return:
    """
    log_prefix      = 'tag_resources'
    sts_client      = context.get_aws_client('sts')
    account_id      = context.obj['caller_id']['Account']
    client          = context.get_aws_client('resourcegroupstaggingapi', region)
    num_resources   = len(resources)
    i               = 1
    context.dlog('[{}]::[started]::[{}]::[number of resources to tag]::[{}]'.format(log_prefix, region, num_resources))

    print('...')
    sleep(.5)
    print('.....')
    sleep(1.5)
    print('.......\n')

    if click.confirm('Before we update the tags would you like to review them?\n'):
        print('\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
        print('++++{ These are the resources that are to be tagged }+++++')
        debug_output(resources)
        print('\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n\n')

        if not click.confirm('Are you ready to save these updates?'):
            debug_exit('Good Bye!')

    for resource_id, tags in resources.items():
        resource_arn    = get_resource_arn(resource_id, region, account_id)
        tags_to_save    = get_resource_tags(context, tags)

        context.dlog('[{}]::[tagging]::[{}]::[{}]::[resource]::[{} of {}]::{}'.format(log_prefix, region, resource_arn, i, num_resources, tags))
        i +=1

        if context.dry_run:
            print('[DRY RUN!]::[{}]::[tagging resource arn]::[{}]::{}'.format(region, resource_arn, tags))
        else:
            print('[CREATED TAGGING]::[{}]::[tagging resource arn]::[{}]::{}'.format(region, resource_arn, tags))
            client.tag_resources(ResourceARNList=[resource_arn], Tags=tags_to_save)

    context.dlog('[{}]::[completed]::[{}]::[number of tagged resources]::[{}]'.format(log_prefix, region, num_resources))


def get_volume_tags(context, region):
    log_prefix  = 'get_volume_tags'
    sts_client  = context.get_aws_client('sts')
    account_id  = context.obj['caller_id']['Account']

    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources_to_tag    = {}
    all_instance_tags   = get_ec2_tags(context, region)
    volumes             = context.get_from_aws_api(
        api_namespace='ec2', api_name='describe_volumes', api_response_key='Volumes',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    # try to name the resource first.
    # if the volume doesn't use a required tag, we look to the attached ec2 node tags in it's place.
    for volume in volumes:
        tags_for_resource = []
        instance_tags = []
        existing_tags = volume['Tags'] if 'Tags' in volume else []
        name_tag = get_by_key_match(existing_tags, 'Key', 'Name', 'Value')

        for instance in volume['Attachments']:
            if instance['InstanceId'] in all_instance_tags:
                instance_tags = all_instance_tags[instance['InstanceId']]
                instance_name = get_by_key_match(instance_tags, 'Key', 'Name', 'Value')

                # tagging the name of the volume to reference attachment's name or instance id if none.
                if not name_tag:
                    name_tag = instance_name if instance_name else instance['InstanceId']
                    tags_for_resource.append({'Key': 'Name', 'Value': '{}'.format(name_tag)})
                break

        if not instance_tags:
            context.dlog('[tag_volumes]::[no parent tags for]::[{}]::[{}]'.format(volume['VolumeId'], region))
            continue

        for tag_key, tag_config in context.tag_configuration.items():
            existing_tag = get_by_key_match(existing_tags, 'Key', tag_config['name'])
            if existing_tag:
                continue

            instance_tag = get_by_key_match(instance_tags, 'Key', tag_config['name'])
            if instance_tag:
                tags_for_resource.append(instance_tag)

        if tags_for_resource:
            resources_to_tag[volume['VolumeId']] = tags_for_resource
        else:
            context.dlog('[tag_volumes]::[no tags updated for]::[{}]'.format(volume['VolumeId'], region))

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_snapshot_tags(context, region):
    log_prefix  = 'get_snapshot_tags'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources_to_tag    = {}
    all_parent_tags     = get_ec2_tags(context, region, ['volume'])
    resources           = context.get_from_aws_api(
        api_namespace='ec2', api_name='describe_snapshots', api_response_key='Snapshots',api_cache_ttl=1,
        api_request_config={'OwnerIds': ['self'], 'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    for resource in resources:
        tags_for_resource   = []
        parent_tags         = []
        existing_tags       = resource['Tags'] if 'Tags' in resource else []
        name_tag            = get_by_key_match(existing_tags, 'Key', 'Name', 'Value')

        # Generate name from the parent resource's Name tag.
        if resource['VolumeId'] in all_parent_tags:
            parent_tags = all_parent_tags[resource['VolumeId']]
            parent_name = get_by_key_match(parent_tags, 'Key', 'Name', 'Value')

            # tagging the name of the volume to reference attachment's name or instance id if none.
            if not name_tag:
                name_tag = parent_name if parent_name else resource['VolumeId']
                if name_tag:
                    tags_for_resource.append({'Key': 'Name', 'Value': '{}'.format(name_tag)})

        if not parent_tags:
            context.dlog('[{}]::[started]::[no parent tags for]::[{}]::[{}]'.format(log_prefix, resource['SnapshotId'], region))
            continue

        for tag_key, tag_config in context.tag_configuration.items():
            existing_tag = get_by_key_match(existing_tags, 'Key', tag_config['name'])
            if existing_tag:
                context.dlog('[tag_snapshots]::[tag already set]::[{}]::[{}]::[{}]'.format(resource['SnapshotId'], region, tag_config['name']))
                continue

            parent_tag = get_by_key_match(parent_tags, 'Key', tag_config['name'])
            if parent_tag:
                tags_for_resource.append(parent_tag)

        if tags_for_resource:
            resources_to_tag[resource['SnapshotId']] = tags_for_resource
        else:
            context.dlog('[tag_snapshots]::[no tags updated for]::[{}]'.format(resource['SnapshotId'], region))

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_rds_instance_snapshot_tags(context, region):
    log_prefix  = 'get_rds_instance_snapshot_tags'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources_to_tag    = {}
    all_parent_tags     = get_rds_instance_tags(context, region)
    resources           = context.get_from_aws_api(
        api_namespace='rds', api_name='describe_db_snapshots', api_response_key='DBSnapshots',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxItems': 9999}}, region=region
    )

    for resource in resources:
        tags_for_resource   = []
        parent_tags         = []
        existing_tags       = resource['TagList'] if 'TagList' in resource else []
        name_tag            = get_by_key_match(existing_tags, 'Key', 'Name', 'Value')

        # Generate name from the parent resource's Name tag.
        if resource['DBInstanceIdentifier'] in all_parent_tags:
            parent_tags = all_parent_tags[resource['DBInstanceIdentifier']]
            parent_name = get_by_key_match(parent_tags, 'Key', 'Name', 'Value')

            # tagging the name of the volume to reference attachment's name or instance id if none.
            if not name_tag:
                name_tag = parent_name if parent_name else resource['DBInstanceIdentifier']
                if name_tag:
                    tags_for_resource.append({'Key': 'Name', 'Value': '{}'.format(name_tag)})

        if not parent_tags:
            context.dlog('[{}]::[no parent tags for]::[{}]::[{}]'.format(log_prefix, resource['DBSnapshotIdentifier'], region))
            continue

        for tag_key, tag_config in context.tag_configuration.items():
            existing_tag = get_by_key_match(existing_tags, 'Key', tag_config['name'])
            if existing_tag:
                context.dlog('[{}]::[tag already set]::[{}]::[{}]::[{}]'.format(log_prefix, resource['DBSnapshotIdentifier'], region, tag_config['name']))
                continue

            parent_tag = get_by_key_match(parent_tags, 'Key', tag_config['name'])
            if parent_tag:
                tags_for_resource.append(parent_tag)

        if tags_for_resource:
            resources_to_tag[resource['DBSnapshotArn']] = tags_for_resource
        else:
            context.dlog('[{}]::[no tags updated fo]::[{}]::[{}]'.format(log_prefix, resource['DBSnapshotIdentifier'], region))

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_rds_cluster_snapshot_tags(context, region):
    log_prefix  = 'get_rds_cluster_snapshot_tags'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources_to_tag    = {}
    all_parent_tags     = get_rds_cluster_tags(context, region)
    resources           = context.get_from_aws_api(
        api_namespace='rds', api_name='describe_db_cluster_snapshots', api_response_key='DBClusterSnapshots',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    for resource in resources:
        tags_for_resource   = []
        parent_tags         = []
        existing_tags       = resource['TagList'] if 'TagList' in resource else []
        name_tag            = get_by_key_match(existing_tags, 'Key', 'Name', 'Value')

        # Generate name from the parent resource's Name tag.
        if resource['DBClusterIdentifier'] in all_parent_tags:
            parent_tags = all_parent_tags[resource['DBClusterIdentifier']]
            parent_name = get_by_key_match(parent_tags, 'Key', 'Name', 'Value')

            # tagging the name of the volume to reference attachment's name or instance id if none.
            if not name_tag:
                name_tag = parent_name if parent_name else resource['DBClusterIdentifier']
                if name_tag:
                    tags_for_resource.append({'Key': 'Name', 'Value': '{}'.format(name_tag)})

        if not parent_tags:
            context.dlog('[{}]::[no parent tags for]::[{}]::[{}]'.format(log_prefix, resource['DBClusterSnapshotIdentifier'], region))
            continue

        for tag_key, tag_config in context.tag_configuration.items():
            existing_tag = get_by_key_match(existing_tags, 'Key', tag_config['name'])
            if existing_tag:
                context.dlog('[{}]::[tag already set]::[{}]::[{}]::[{}]'.format(log_prefix, resource['DBClusterSnapshotIdentifier'], region, tag_config['name']))
                continue

            parent_tag = get_by_key_match(parent_tags, 'Key', tag_config['name'])
            if parent_tag:
                tags_for_resource.append(parent_tag)

        if tags_for_resource:
            resources_to_tag[resource['DBClusterSnapshotArn']] = tags_for_resource
        else:
            context.dlog('[{}]::[no tags updated fo]::[{}]::[{}]'.format(log_prefix, resource['DBClusterSnapshotIdentifier'], region))

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def tag_inheritable_resources(context):
    log_prefix  = 'tag_inheritable_resources'
    sts_client  = context.get_aws_client('sts')
    account_id  = context.obj['caller_id']['Account']
    dry_run     = context.dry_run
    regions     = context.regions
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, account_id))

    if dry_run:
        context.dlog('[{}]::[dry_run]::[{}]'.format(log_prefix, account_id))

    for region in regions:
        context.dlog('[{}]::[dry_run]::[{}]::[started region]::[{}]'.format(log_prefix, account_id, region))

        # order of operations (volumes, snapshots) required to ensure snaps can use volume tags if available.
        resources_to_tag    = {}
        print('')
        print('==================================================================')
        print('Checking for inheritable resources to tag in [{}]...'.format(region))

        resources   = get_volume_tags(context, region)
        resources_to_tag.update(resources)
        print('Found [{}] [Volumes] to tag in [{}]'.format(len(resources), region))

        resources   = get_snapshot_tags(context, region)
        resources_to_tag.update(resources)
        print('Found [{}] [EC2 Snapshots] to tag in [{}]'.format(len(resources), region))

        resources   = get_rds_instance_snapshot_tags(context, region)
        resources_to_tag.update(resources)
        print('Found [{}] [RDS Instance Snapshots] to tag in [{}]'.format(len(resources), region))

        resources   = get_rds_cluster_snapshot_tags(context, region)
        resources_to_tag.update(resources)
        print('Found [{}] [RDS Cluster Snapshots] to tag in [{}]'.format(len(resources), region))

        num_resources   = len(resources_to_tag)
        print('')
        print('==================================================================')

        if resources_to_tag:
            print('Tagging::[inheritable_resources]::[found]::[{}]::[inheritable_resources]'.format(region, num_resources))
            tag_resources(context, resources_to_tag, region)
        else:
            print('Skipping::[inheritable_resources]::[found]::[{}]::[inheritable_resources]'.format(region, num_resources))

        context.dlog('[{}]::[completed region]::[{}]::[started region]::[{}]'.format(log_prefix, account_id, region))

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, account_id))


def ask_tag_value(context, tag_config, current_tag_value = None):
    """
    Friendly manner to ask for tag values, provide insight into tag requirements, and do some validation of the value.
    :param context:
    :param tag_config:
    :return:
    """
    log_prefix  = 'tag_inheritable_resources'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, current_tag_value))

    question    = '\nTag Name: [{}] \nPurpose: {}\nExamples: ({})\nEnter a value for ({}) '.format(
        tag_config['name'], tag_config['purpose'], tag_config['examples'], tag_config['name']
    )

    if context.expert_mode:
        question = 'Enter a value for ({}) '.format(tag_config['name'])

    if not 'changed_values' in tag_config:
        context.dlog('[{}]::[changed_values]::[created]'.format(log_prefix))
        tag_config['changed_values']    = {}

    if tag_config['allowed_values']:

        # behavior added to help normalize values based on the allowed tags values.
        # this results in the existing tag being replaced with the format of the allowed tags.
        if current_tag_value:
            for allowed_value in tag_config['allowed_values']:
                if current_tag_value.lower() == allowed_value.lower():
                    current_tag_value = allowed_value
                    break

        # if there's no existing tag, we'll try to guess by finding the last time this tag was defined.
        elif tag_config['name'] in tag_config['changed_values']:
            context.dlog('[{}]::[changed_values]::[matched for]::[{}]'.format(log_prefix, current_tag_value))
            current_tag_value   = tag_config['changed_values'][tag_config['name']]

        if not context.expert_mode:
            question = '\nTag Name:[{}] \nPurpose: {}\nAllowed Values: ({})\nEnter a value for "{}" '.format(
                tag_config['name'], tag_config['purpose'], ', '.join(tag_config['allowed_values']), tag_config['name']
            )

    # time to find out what the user might want, passing a current value or guessed value as a preset default.
    tag_value = get_input(context, question, current_tag_value)

    if tag_config['allowed_values'] and tag_value != current_tag_value:
        tag_config['changed_values'][tag_config['name']] = tag_value

    if tag_config['allowed_values'] and tag_value not in tag_config['allowed_values']:
        print('ERROR!! Chosen Value not allowed.')
        tag_value = ask_tag_value(context, tag_config, current_tag_value)

    if tag_config['required'] and tag_value == '':
        print('ERROR!! Value must not be empty.')
        tag_value = ask_tag_value(context, tag_config, current_tag_value)

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, tag_value))
    return tag_value


def get_input(context, value, default_value = None):
    return validate_input(context, click.prompt(value, default=default_value))


def validate_input(context, value):
    if value.lower() == 'exit' or value.lower() == 'quit':
        print('\n\n')
        print('{-------------------------}  ')
        print('{----[This is the way]----}  ')
        print('{-------------------------}  ')
        if context.expert_mode:
            print('{                         }  ')
            print('{----[  ]---------[ ]-----}  ')
            print('{                         }  ')
            print('{           ---           }  ')
            print('{                         }  ')
            print('(    )---------------(    )  ')
            print('{                         }  ')
            print('{-------------------------}  ')
        sys.exit()
    return value


def get_tag_config(context, tag):
    """
    Helper to get access to match a string name tag to the configuration.
    :param tag:
    :return:
    """
    for key, tag_config in context.tag_configuration.items():
        if tag == tag_config['name']:
            return tag_config


def get_tag_answers(context, resource_tags, service_name = None):
    log_prefix = 'get_tag_answers'
    context.dlog('[{}]::[started]'.format(log_prefix))
    tags_to_save    = []

    for tag_key,tag_config in context.tag_configuration.items():
        if service_name in tag_config['hide_for_services']:
            context.dlog('[{}]::[{}]::[tag is hidden for this service]::[{}]'.format(log_prefix, tag_config['name'], service_name))
            continue

        current_tag_value   = get_by_key_match(resource_tags, 'Key', tag_config['name'], 'Value')

        # Lets attempt to use another tag that was already set for the current value.
        if not current_tag_value and tag_config['allow_values_from']:
            for allow_values_from in tag_config['allow_values_from']:
                current_tag_value = get_by_key_match(tags_to_save, 'Key', allow_values_from, 'Value')
                if current_tag_value:
                    break

        # customized service tagging based on service passed.
        if not current_tag_value and tag_key == 'service' and service_name:
            current_tag_value = service_name

        tag_value = ask_tag_value(context, tag_config, current_tag_value)
        if tag_value:
            context.dlog('[{}]::[tags_to_save]::[{}]::[{}]'.format(log_prefix, tag_config['name'], tag_value))
            tags_to_save.append({'Key': tag_config['name'], 'Value': tag_value})

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, tags_to_save))

    return tags_to_save


def get_ecr_resources(context, region):
    log_prefix          = 'get_ecr_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='ecr', api_name='describe_repositories', api_response_key='repositories', api_cache_ttl=1,
        api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    for resource in resources:
        tags = context.get_from_aws_api(
            api_namespace='ecr', api_name='list_tags_for_resource', api_response_key='tags',
            api_cache_ttl=1,
            api_request_config={'resourceArn': resource['repositoryArn']}, region=region
        )
        resources_to_tag[resource['repositoryArn']]   = tags if tags else []

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_efs_resources(context, region):
    log_prefix          = 'get_efs_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='efs', api_name='describe_file_systems', api_response_key='FileSystems', api_cache_ttl=1,
        api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    for resource in resources:
        resources_to_tag[resource['FileSystemArn']]   = resource['Tags'] if 'Tags' in resource else []

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_ec2_asg_resources(context, region):
    log_prefix          = 'get_ec2_asg_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='autoscaling', api_name='describe_auto_scaling_groups', api_response_key='AutoScalingGroups', api_cache_ttl=1,
        api_request_config={'PaginationConfig': {'MaxRecords': 99999}}, region=region
    )

    for resource in resources:
        resources_to_tag[resource['AutoScalingGroupARN']]   = resource['Tags'] if 'Tags' in resource else []

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_ec2_resources(context, region):
    log_prefix          = 'get_ec2_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='ec2', api_name='describe_instances', api_response_key='Reservations', api_cache_ttl=1,
        api_request_config={'PaginationConfig': {'MaxResults': 99999}}, region=region
    )

    for reservation in resources:
        for resource in reservation['Instances']:
            resources_to_tag[resource['InstanceId']] = resource['Tags'] if 'Tags' in resource else []

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_loadbalancer_resources(context, region):
    """
    Abstract the two API's for Classic ELB and New-Age LB.
    :param context:
    :param region:
    :return:
    """
    log_prefix          = 'get_elb_resources'
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))
    resources_to_tag    = {}
    resources_to_tag.update(get_elb_resources(context, region))
    resources_to_tag.update(get_lb_resources(context, region))
    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag

def get_normalized_tags(context, resource_tags):
    tags = []

    try:
        for tag in resource_tags:
            tags.append({'Key': tag['Key'], 'Value': tag['Value']})

    except TypeError:
        for tag,val in resource_tags.items():
            tags.append({'Key': tag, 'Value': val})

    return tags


def get_resource_tags(context, resource_tags):
    """
    Functionality defined to ensure a proper format for resource tags to be saved.
    This is required because AWS sometimes likes to be inconsistent in their data structures for tagging.
    :param context:
    :param resource_tags:
    :return:
    """
    tags = {}

    try:
        for tag in resource_tags:
            tags[tag['Key']] = tag['Value']

    except TypeError:
        for tag,val in resource_tags.items():
            tags[tag] = val

    return tags


def get_lb_resources(context, region):
    log_prefix          = 'get_lb_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    load_balancers = context.get_from_aws_api(
        api_namespace='elbv2', api_name='describe_load_balancers', api_response_key='LoadBalancers',
        api_cache_ttl=300, api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    for load_balancer in load_balancers:
        try:
            lb_tags = context.get_from_aws_api(
                api_namespace='elbv2', api_name='describe_tags', api_response_key='TagDescriptions', api_cache_ttl=1,
                api_request_config={'ResourceArns': [load_balancer['LoadBalancerArn']]}, region=region
            )
            lb_tags = lb_tags[0]['Tags']
        except botocore.exceptions.ClientError as error:
            context.dlog('[{}]::[resource has no tags]::[{}]::[{}]'.format(log_prefix, region, load_balancer['LoadBalancerArn']))
            lb_tags = []

        resources_to_tag[load_balancer['LoadBalancerArn']] = lb_tags

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_elb_resources(context, region):
    log_prefix          = 'get_elb_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    load_balancers = context.get_from_aws_api(
        api_namespace='elb', api_name='describe_load_balancers', api_response_key='LoadBalancerDescriptions',
        api_cache_ttl=300, api_request_config={'PaginationConfig': {'MaxResults': 99999}}, region=region
    )

    for load_balancer in load_balancers:
        try:
            lb_tags = context.get_from_aws_api(
                api_namespace='elb', api_name='describe_tags', api_response_key='TagDescriptions', api_cache_ttl=1,
                api_request_config={'LoadBalancerNames': [load_balancer['LoadBalancerName']]}, region=region
            )
            lb_tags = lb_tags[0]['Tags']
        except botocore.exceptions.ClientError as error:
            context.dlog('[{}]::[resource has no tags]::[{}]'.format(log_prefix, region))
            lb_tags = []

        # prefix in order to generate an arn from this later, api doesn't return the arn for some hurtful reason.
        # they also don't return tags either, see how we had to make another api call just for them? :(
        resources_to_tag['elb-{}'.format(load_balancer['LoadBalancerName'])] = lb_tags

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_elastic_search_resources(context, region):
    log_prefix          = 'get_elasticache_tags'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    domains_available = context.get_from_aws_api(
        api_namespace='es', api_name='list_domain_names', api_response_key='DomainNames', api_cache_ttl=3600,
        api_request_config={}, region=region
    )

    domain_list = []
    for item in domains_available:
        domain_list.append(item['DomainName'])

    domains = context.get_from_aws_api(
        api_namespace='es', api_name='describe_elasticsearch_domains', api_response_key='DomainStatusList',
        api_cache_ttl=3600, api_request_config={'DomainNames': domain_list}, region=region
    )

    for domain in domains:
        context.dlog('[{}]::[domain]::[{}]::[{}]'.format(log_prefix, region, domain['DomainName']))
        try:
            tags_for_resource = context.get_from_aws_api(
                api_namespace='es', api_name='list_tags', api_response_key='TagList', api_cache_ttl=1,
                api_request_config={'ARN': domain['ARN']}, region=region
            )
        except botocore.exceptions.ClientError as error:
            context.dlog('[tag_es]::[resource has no tags]::[{}]'.format(error))
            tags_for_resource = []

        resources_to_tag[domain['ARN']] = tags_for_resource

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_elasticache_resources(context, region):
    log_prefix          = 'get_elasticache_tags'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))
    cache_clusters  = context.get_from_aws_api(
        api_namespace='elasticache',  api_name='describe_cache_clusters', api_response_key='CacheClusters',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxRecords': 99999}, 'ShowCacheNodeInfo': True},
        region=region
    )

    for cache_cluster in cache_clusters:
        context.dlog('[{}]::[cache_cluster]::[{}]'.format(log_prefix, cache_cluster['CacheClusterId']))
        try:
            tags_for_resource = context.get_from_aws_api(
                api_namespace='elasticache', api_name='list_tags_for_resource', api_response_key='TagList',
                api_cache_ttl=1, api_request_config={'ResourceName': cache_cluster['ARN']}, region=region
            )
        except botocore.exceptions.ClientError as error:
            context.dlog('[{}]::[resource has no tags]::[{}]'.format(log_prefix, format(error)))
            tags_for_resource = []

        resources_to_tag[cache_cluster['ARN']] = tags_for_resource

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_s3_resources(context, region):
    log_prefix          = 'get_s3_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    s3_buckets = context.get_from_aws_api(
        api_namespace='s3', api_name='list_buckets', api_response_key='Buckets', api_cache_ttl=1,
        api_request_config={}, region=region
    )

    for s3_bucket in s3_buckets:
        context.dlog('[{}]::[s3_bucket]::[{}]::[{}]'.format(log_prefix, region, s3_bucket['Name']))
        try:
            tags_for_resource    = context.get_from_aws_api(
                api_namespace='s3', api_name='get_bucket_tagging', api_response_key='TagSet', api_cache_ttl=1,
                api_request_config={'Bucket': s3_bucket['Name']}, region=region
            )
        except botocore.exceptions.ClientError as error:
            context.dlog('[{}]::[s3_bucket has no tags]::[{}]::[{}]'.format(log_prefix, region, error))
            tags_for_resource  = []

        resources_to_tag['s3-{}'.format(s3_bucket['Name'])] = tags_for_resource

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_rds_resources(context, region):
    log_prefix          = 'get_s3_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    instances = context.get_from_aws_api(
        api_namespace='rds', api_name='describe_db_instances', api_response_key='DBInstances', api_cache_ttl=3600,
        api_request_config={'PaginationConfig': {'MaxRecords': 99999}}, region=region
    )

    for db_instance in instances:
        context.dlog('[{}]::[instance]::[{}]'.format(log_prefix, db_instance['DBInstanceArn']))
        db_instance_name    = db_instance['DBInstanceIdentifier'] if 'DBInstanceIdentifier' in db_instance else None
        db_instance_arn     = db_instance['DBInstanceArn'] if 'DBInstanceArn' in db_instance else None
        db_cluster_name     = db_instance['DBClusterIdentifier'] if 'DBClusterIdentifier' in db_instance else None
        db_cluster_arn      = None
        tags_for_cluster    = []
        tags_for_instance   = []

        try:
            tags_for_instance = context.get_from_aws_api(
                api_namespace='rds', api_name='list_tags_for_resource', api_response_key='TagList', api_cache_ttl=1,
                api_request_config={'ResourceName': db_instance_arn}, region=region
            )
        except botocore.exceptions.ClientError as error:
            context.dlog('[{}]::[resource has no tags]::[{}]'.format(log_prefix, error))

        if db_cluster_name:
            db_cluster_arn = db_instance_arn.replace(':db:' + db_instance_name, ':cluster:' + db_cluster_name)
            try:
                tags_for_cluster    = context.get_from_aws_api(
                    api_namespace='rds', api_name='list_tags_for_resource', api_response_key='TagList', api_cache_ttl=1,
                    api_request_config={'ResourceName': db_cluster_arn}, region=region
                )
            except botocore.exceptions.ClientError as error:
                context.dlog('[tag_rds]::[resource has no tags]::[{}]'.format(error))

        if db_instance_arn:
            resources_to_tag[db_instance_arn] = tags_for_instance

        if db_cluster_arn:
            resources_to_tag[db_cluster_arn] = tags_for_cluster

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_redshift_resources(context, region):
    log_prefix          = 'get_s3_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='redshift', api_name='describe_clusters', api_response_key='Clusters',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxRecords': 99999}}, region=region
    )

    for resource in resources:
        resources_to_tag['redshift-{}'.format(resource['ClusterIdentifier'])] = resource['Tags'] if 'Tags' in resource else []

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_lambda_resources(context, region):
    log_prefix          = 'get_lambda_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='lambda', api_name='list_functions', api_response_key='Functions',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    for resource in resources:
        try:
            tags_for_resource = context.get_from_aws_api(
                api_namespace='lambda', api_name='list_tags', api_response_key='Tags', api_cache_ttl=1,
                api_request_config={'Resource': resource['FunctionArn']}, region=region
            )
        except botocore.exceptions.ClientError as error:
            context.dlog('[{}]::[resource has no tags]::[{}]'.format(log_prefix, error))
            tags_for_resource = []

        resources_to_tag[resource['FunctionArn']] = get_normalized_tags(context, tags_for_resource)

    context.dlog('[{}]::[completed]::[{}]'.format(log_prefix, region))
    return resources_to_tag


def get_pinpoint_resources(context, region):
    log_prefix          = 'get_pinpoint_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='pinpoint', api_name='get_apps', api_response_key='ApplicationsResponse',
        api_cache_ttl=1, api_request_config={}, region=region
    )

    if resources and 'Item' in resources:
        for resource in resources['Item']:
            resources_to_tag[resource['Arn']] = get_normalized_tags(context, resource['tags'])

    return resources_to_tag


def get_cloudfront_resources(context, region):
    log_prefix          = 'get_cloudfront_resources'
    resources_to_tag    = {}
    context.dlog('[{}]::[started]::[{}]'.format(log_prefix, region))

    resources = context.get_from_aws_api(
        api_namespace='cloudfront', api_name='list_distributions', api_response_key='DistributionList',
        api_cache_ttl=1, api_request_config={'PaginationConfig': {'MaxItems': 99999}}, region=region
    )

    if resources and 'Items' in resources:
        for resource in resources['Items']:
            try:
                tags_for_resource = context.get_from_aws_api(
                    api_namespace='cloudfront', api_name='list_tags_for_resource', api_response_key='Tags', api_cache_ttl=1,
                    api_request_config={'Resource': resource['ARN']}, region=region
                )
                tags_for_resource   = tags_for_resource['Items'] if 'Items' in tags_for_resource else []
            except botocore.exceptions.ClientError as error:
                context.dlog('[{}]::[resource has no tags]::[{}]'.format(log_prefix, error))
                tags_for_resource = []

            resources_to_tag[resource['ARN']] = get_normalized_tags(context, tags_for_resource)

    return resources_to_tag


def tag_service_resources(context, service, region):
    log_prefix = 'tag_service_resources_v2'
    context.dlog('[{}]::[starting]::[{}]::[{}]'.format(log_prefix, service, region))
    resources_to_tag    = {}
    sts_client          = context.get_aws_client('sts')
    account_id          = context.obj['caller_id']['Account']

    # the returned data should be {resource_id = [{'Key':'Example', Value:'Value'}]}
    supported_services    = {
        'elasticache':  get_elasticache_resources,
        'ec2':          get_ec2_resources,
        'ec2:asg':      get_ec2_asg_resources,
        'ecr:repos':    get_ecr_resources,
        'elb':          get_loadbalancer_resources,
        'es':           get_elastic_search_resources,
        's3':           get_s3_resources,
        'rds':          get_rds_resources,
        'redshift':     get_redshift_resources,
        'efs':          get_efs_resources,
        'lambda':       get_lambda_resources,
        'pinpoint':     get_pinpoint_resources,
        'cloudfront':   get_cloudfront_resources
    }

    # send to legacy service handler.
    if service not in supported_services:
        context.dlog('[{}]::[ERROR]::[unsupported service]::[{}]::[{}]'.format(log_prefix, service, region))
        print('Yikes!! "{}" in "{}", is not yet a supported service of this tagging tool, please do not do that again.'.format(service, region))
        return

    print('')
    print('Please hang tight while I contemplate if I should find your [{}]::[{}] data...'.format(region, service))
    resources   = supported_services[service](context, region)

    if resources:
        print('')
        print('===================================================================================')
        print('= Press [ENTER] or [RETURN] to accept prefilled suggestion or existing tag value. =')
        print('= Type "exit" or "quit" at any prompt and the program will stop running.          =')
        print('===================================================================================')
    else:
        print('...No resources found for [{}]::[{}]'.format(region, service))

    for resource_id, existing_tags in resources.items():
        print('')
        print('===================================================================================')
        resource_arn    = get_resource_arn(resource_id, region, account_id)
        name_tag        = get_by_key_match(existing_tags, 'Key', 'Name', 'Value')
        print('Setting Tags For::[{}]::[{}]::[{}]::[{}]::[{}]'.format(service, region, resource_id, name_tag, resource_arn))
        resources_to_tag[resource_id]   = get_tag_answers(context, existing_tags, service)

    num_resources = len(resources_to_tag)

    print('')
    print('==================================================================')

    if num_resources > 0:
        print('Tagging::[{}]::[{}]::[found]::[{}]::[resources]'.format(region, service, num_resources))
        tag_resources(context, resources_to_tag, region)
    else:
        print('Skipping::[{}]::[{}]::[found]::[{}]::[resources]'.format(region, service, num_resources))

    context.dlog('[{}]::[completed]::[{}]::[{}]'.format(log_prefix, service, region))


#-{CLI Commands}-------------------------------------------------------------------------------------------------------#

@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@click.option('-y', '--dry-run', envvar='DRY_RUN', is_flag=True, default=False, help='Enables a Dry run (no changes)')
@pass_context
def subcmd(context, profile, verbose, debug, dry_run):
    """does stuff for you."""
    context.obj['aws_profile']  = profile
    context.verbose             = verbose
    context.debug               = debug
    context.dry_run             = dry_run
    context.dlog('[{}].[{}].[{}].[{}]'.format(profile, verbose, debug, dry_run))

@subcmd.command()
@click.option('--services', envvar='services', multiple=True, default=['ec2', 'ec2:asg', 'ecr:repos', 'efs', 'rds', 'es', 'elasticache', 'redshift', 's3', 'elb', 'lambda', 'pinpoint', 'cloudfront'], help='Optionally, define services to tag.')
@click.option('--regions', envvar='services', multiple=True, default=['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2'], help='Optionally, define specific regions to tag.')
@click.option('--skip-region-prompts', envvar='SKIP_PROMPT', is_flag=True, default=False, help='Skips the region prompts.')
@click.option('--skip-inheritable-tagging', envvar='SKIP_INHERITABLE_TAGGING', is_flag=True, default=False, help='Skips the inheritable tagging.')
@click.option('--skip-service-tagging', envvar='SKIP_SERVICE_TAGGING', is_flag=True, default=False, help='Skips the main service tagging.')
@click.option('--expert-mode', envvar='EXPERT_MODE', is_flag=True, default=False, help='if you have to ask....')
@pass_context
def interactive(context, services, regions, skip_region_prompts, skip_inheritable_tagging, skip_service_tagging, expert_mode):
    """
    :param context:
    :param services:
    :param regions:
    :param skip_region_prompts:
    :param skip_inheritable_tagging:
    :param skip_service_tagging:
    :param expert_mode:
    :return:
    """
    context.expert_mode = expert_mode
    context.services    = services
    context.regions     = regions
    context.dlog('[interactive]::[started]::[]'.format())

    # can and should we get this data from aws for our required tags?
    # name added for consistency, if it's an issue we can try it as a not required tag or just disable it.
    context.tag_configuration   = {
        'name': {
            'name': 'Name',
            'required': True,
            'allowed_values': [],
            'purpose': 'All things should be named.',
            'examples': 'halo-api',
            'allow_values_from': [],
            'hide_for_services': ['s3', 'rds', 'redshift', 'ec2:asg']
        },
        'application': {
            'name': 'Application',
            'required': True,
            'allowed_values': [],
            'purpose': 'Define the name that the resource is a part of, (this is the same as the Platform, we support both for now).',
            'examples': 'MyApplication',
            'allow_values_from': ['Platform'],
            'hide_for_services': []
        },
        'platform': {
            'name': 'Platform',
            'required': True,
            'allowed_values': [],
            'purpose': 'Define the overall platform that the resource belongs to; this is a business level tag we use to track costs across a group of services that comprises a single platform. ',
            'examples': 'MyApplication',
            'allow_values_from': ['Application'],
            'hide_for_services': []
        },
        'environment': {
            'name': 'Environment',
            'required': True,
            'allowed_values': ['Development', 'Production', 'Stage', 'Test', 'QA', 'UAT'],
            'purpose': 'Define the hosting enviornment perimeter. These tags are used in some automation efforts, security controls, and for cost tracking.',
            'examples': '',
            'allow_values_from': ['Stage', 'ENV', 'ENV_NAME'],
            'hide_for_services': []
        },
        'service': {
            'name': 'Service',
            'required': True,
            'allowed_values': [],
            'purpose': 'Define what type of resource is being used.',
            'examples': 'db, lb, logging, web',
            'allow_values_from': ['SYSTEM', 'project'],
            'hide_for_services': []
        }
    }

    context.dlog('[interactive]::[regions]::[{}]'.format(regions))
    context.dlog('[interactive]::[all_services]::[{}]'.format(services))
    context.dlog('[interactive]::[tag_configuration]::[{}]'.format(context.tag_configuration))

    if context.dry_run:
        context.dlog('[interactive]::[dry_run]::[{}]'.format(context.dry_run))

    print('\n\n****************************************************')
    print('***  Hi! Lets start tagging your AWS resources!  ***')

    if context.dry_run:
        print("***  JUST KIDDING, YOU ASKED FOR A DRY RUN...    ***")
        print("***  WHICH MEANS NO TAGGING WILL BE ADDED...     ***")

    if context.expert_mode:
        print("***  [expert mode, engage!]                      ***")

    print("****************************************************")

    print('* ')
    print('* ')
    print('* This version supports following regions, services, tags:')
    print('* ')
    print('* [regions]::{}'.format(regions))
    print('* [services]::{}'.format(services))
    print('* ')
    print('**************************************************')
    print('  ')

    global_services = ['s3', 'cloudfront']
    completed_global_services   = []

    if not skip_service_tagging:
        for service in services:
            for region in regions:
                # some services are global and we'll just touch them the first pass through.
                if service in global_services and service in completed_global_services:
                    continue

                if not skip_region_prompts:
                    ch = get_input(context, 'Tagging [{}] service in [{}]\n[Y]Start or [N]Skip to next region?'.format(service, region))
                    try:
                        ch = str(ch).lower().strip()[0]
                    except:
                        ch = 'n'
                        pass
                    if ch == 'y':
                        print('')
                        tag_service_resources(context, service, region)
                    else:
                        pass
                else:
                    tag_service_resources(context, service, region)

                # track usage of a global service to ensure it went through at least once.
                if service in global_services and service not in completed_global_services:
                    completed_global_services.append(service)

    if not skip_inheritable_tagging:
        context.dlog('[interactive]::[tag_inheritable_resources]::[started]')
        tag_inheritable_resources(context)
        context.dlog('[interactive]::[tag_inheritable_resources]::[completed]')

    print('\n\n***  Stay frosty my friend, we are all done now.  ***')
    print("*********************************************************")

    context.dlog('[interactive]::[completed]'.format())
