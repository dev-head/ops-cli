import click
import boto3
import os
import json
import yaml
import socket
from cli import pass_context
import cffi
from fabric import Connection
from fabric import ThreadingGroup
from paramiko import SSHException
from invoke import UnexpectedExit
from datetime import datetime
import sys
from pathlib import Path
import copy
import botocore

# -{Command Function/Classes}------------------------------------------------------------------------------------------#

def debug_exit(o):
    debug_output(o)
    sys.exit()


def debug_output(o):
    print(json.dumps(o, indent=4, sort_keys=True, default=str))


def get_security_groups_by_filters(ctx, filters, cache_ttl= 0, max_results=5,
                                   api_name='ec2', api_call='describe_security_groups'):
    return ctx.get_from_aws_api(
        api_namespace       = api_name,
        api_name            = api_call,
        api_response_key    = 'SecurityGroups',
        api_cache_ttl       = cache_ttl,
        api_request_config  = {'Filters': filters, 'PaginationConfig': {'MaxResults': max_results}}
    )


def connectionGroupRun(ctx, connections, plan):
    log_prefix = '[connectionGroupRun]'.format()
    ctx.dlog('{}::[started]'.format(log_prefix))
    ctx.dlog('{}::[num connections]::[{}]'.format(log_prefix, str(len(connections))))
    results = []

    group   = ThreadingGroup.from_connections(connections)
    with click.progressbar(group, label='Running plans against connections.') as group_bar:
        for connection in group_bar:
            result_plan = fabric_run_plan(ctx, connection, plan)
            result = {'connection': connection.host, 'results': result_plan}
            results.append(result)

    ctx.dlog('{}::[num results]::[{}]'.format(log_prefix, str(len(results))))
    ctx.dlog('{}::[completed]'.format(log_prefix))

    return results


def buildConnectionsFromInstanceData(ctx, instance_data, connect_timeout=10):
    log_prefix = '[buildConnections]'.format()
    ctx.dlog('{}::[started]'.format(log_prefix))
    ctx.dlog('{}::[num instances]::[{}]'.format(log_prefix, str(len(instance_data))))
    ctx.dlog('{}::[connect_timeout]::[{}]'.format(log_prefix, str(connect_timeout)))
    connections = []

    for instance in instance_data:
        if 'ops_metadata' in instance and 'ssh_keys' in instance['ops_metadata'] and len(instance['ops_metadata']['ssh_keys']) > 0:
            for key_data in instance['ops_metadata']['ssh_keys']:

                if 'user' not in key_data or 'local_path' not in key_data or 'host' not in key_data:
                    ctx.dlog('{}::[error]::[key data is missing for]::[{}]'.format(log_prefix, str(instance['InstanceId'])))
                    continue

                connection  = Connection(key_data['host'],
                                         user=key_data['user'],
                                         connect_timeout=connect_timeout,
                                         connect_kwargs={'key_filename': key_data['local_path']}
                                         )
                connections.append(connection)
                break;  # first ssh key we find is good enough.

    ctx.dlog('{}::[num connections]::[{}]'.format(log_prefix, str(len(connections))))
    ctx.dlog('{}::[started]'.format(log_prefix))
    return connections


def fabric_run_plan(ctx, connection, plan_data):
    log_prefix  = '[fabric_run_plan]::[{}]'.format(connection.host)
    results  = {
        'upload_file': [],
        'command': []
    }

    ctx.vlog('{}::[starting]'.format(log_prefix))

    if 'upload_files' in plan_data:
        ctx.vlog('{}::[starting file upload]'.format(log_prefix))

        for file in plan_data['upload_files']:
            source  = file['source'] if 'source' in file else None
            dest    = file['destination'] if 'destination' in file else '.'
            if source is not None:

                try:
                    connection.put(source, remote=dest)
                    result  = {
                        'source': source,
                        'destination': dest,
                        'response': {
                            'raw': 'file upload successful',
                            'stripped': 'file upload successful',
                            'status': 0,
                            'timestamp': str(datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC')),
                        }
                    }
                except Exception as e:
                    result  = {
                        'source': source,
                        'destination': dest,
                        'response': {
                            'raw': None,
                            'error': str(e),
                            'status': 1,
                            'timestamp': str(datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC')),
                        }
                    }

                ctx.vlog('{}::[uploaded]::[source]::[{}]::[destination]::[{}]::[status]::[{}]'.format(log_prefix, source, dest, result['response']['status']))
                results['upload_file'].append(result)

    if 'run' in plan_data:
        ctx.vlog('{}::[starting command exec]'.format(log_prefix))

        for execute_command in plan_data['run']:
            try:

                result_run = connection.run(execute_command, hide ='both')
                result = {
                    'command': execute_command,
                    'response': {
                        'raw': result_run,
                        'stripped': result_run.stdout.strip(),
                        'error': result_run.stderr.strip(),
                        'status': result_run.exited,
                        'timestamp': str(datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC')),
                    }
                }
            except (socket.timeout, UnexpectedExit) as e:
                result = {
                    'command': execute_command,
                    'response': {
                        'raw': None,
                        'stripped': None,
                        'status': 1,
                        'timestamp': str(datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC')),
                        'error': str(e),
                    }
                }

            ctx.vlog('{}::[execute_command]::[executed]::[{}]::[status]::[{}]'.format(log_prefix, execute_command, result['response']['status']))
            results['command'].append(result)
    return results


def testInstanceSshUser(ctx, instance, ssh_key, user, **kwargs):
    log_prefix      = '[testInstanceSshUser]'.format()
    host            = instance['PublicIpAddress']
    test_command    = kwargs.get('test_command', 'hostname')
    key_name        = os.path.splitext(os.path.basename(ssh_key))[0]
    connect_timeout = kwargs.get('connect_timeout', 10)
    ctx.dlog('{}::[started]::[{}]::[{}]::[{}]::[{}]::[{}]'.format(log_prefix, ssh_key, user, host, test_command, str(connect_timeout)))
    result    = None

    try:
        response = Connection(host, user=user, connect_timeout=connect_timeout,
                            connect_kwargs={'key_filename': ssh_key}).run(test_command, hide='both')
        result = {
                'connection_string': 'ssh -i {} {}@{}'.format(ssh_key, user, host),
                'local_path': ssh_key,
                'user': user,
                'host': host,
                'created': str(datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC')),
                'key_name': key_name,
                'command': {
                    'exec': test_command,
                    'response': response.exited,
                    'output': response.stdout.strip()
                }
            }
        ctx.dlog('{}::[ssh]::[confirmed key]::[ssh -i {} {}@{}]::[{}]::[{}]'.format(log_prefix, ssh_key, user, host, response.exited, response.stdout.strip()))
    except SSHException as e:
        ctx.dlog("{}::[ssh]::[key failed]::[ssh -i {} {}@{}]::[{}]".format(log_prefix, ssh_key, user, host, str(e)))
        result = None
        # pass
    except ValueError as e:
        ctx.dlog("{}::[ssh]::[python library failed]::[ssh -i {} {}@{}]::[{}]".format(log_prefix, ssh_key, user, host, str(e)))
        result = None
        # pass
    except Exception as e:
        ctx.dlog("{}::[ssh]::[host failed]::[ssh -i {} {}@{}]::[{}]".format(log_prefix, ssh_key, user, host, str(e)))
        result = None

    ctx.dlog('{}::[completed]'.format(log_prefix))
    return result


def testInstanceSshKey(ctx, instance, ssh_key, **kwargs):
    log_prefix = '[testInstanceSshKey]'.format()
    ctx.dlog('{}::[started]'.format(log_prefix))
    users_expected     = kwargs.get('user_names', ['ubuntu', 'ec2-user', 'openvas', 'root'])
    users_preferred     = kwargs.get('user_names_preferred', ['ubuntu', 'ec2-user'])
    break_on_preferred  = kwargs.get('break_on_preferred', True)

    valid_ssh_keys      = []

    for user in users_expected:
        result = testInstanceSshUser(ctx, instance, ssh_key, user)

        if result is not None:
            valid_ssh_keys.append(result)

            if break_on_preferred is True and user in users_preferred:
                break

    ctx.dlog('{}::[completed]'.format(log_prefix))
    return valid_ssh_keys


def testInstanceSshKeys(ctx, instance, ssh_keys, **kwargs):
    log_prefix = '[testInstanceSshKeys]'.format()
    ctx.dlog('{}::[started]'.format(log_prefix))
    break_on_preferred  = kwargs.get('break_on_preferred', True)
    valid_ssh_keys  = []

    for ssh_key in ssh_keys:
        ctx.dlog('{}::[testing ssh key]::[{}]'.format(log_prefix, ssh_key))
        result  = testInstanceSshKey(ctx, instance, ssh_key, break_on_preferred = break_on_preferred)

        if result is not None and len(result) > 0:
            valid_ssh_keys  = valid_ssh_keys + result

            if break_on_preferred is True:
                ctx.dlog('{}::[i was told to break]::[{}]'.format(log_prefix, result))
                break

    if 'ops_metadata' not in instance:
        instance['ops_metadata'] = {}

    instance['ops_metadata']['ssh_keys'] = valid_ssh_keys
    ctx.dlog('{}::[completed]'.format(log_prefix))
    return instance


def describeSshKeys(path, prefix = '', suffix = '.priv'):
    rv  = []
    for filename in os.listdir(path):
        if filename.endswith(suffix) and filename.startswith(prefix):
            rv.append(os.path.join(path, filename))
    rv.sort()
    return rv


def describeInstances(ctx, limit = 1, filters = None):
    """
    AWS Api returns results in unexplained groupings of Reservations, here we break
    that up and normalize it into a single list of instances...this is the way.
    :param ctx:
    :param limit:
    :param filters:
    :return:
    """
    instance_data = ctx.get_from_aws_api(
        api_namespace       = 'ec2',
        api_name            = 'describe_instances',
        api_response_key    = 'Reservations',
        api_cache_ttl       = 3600,
        api_request_config  = {
            'Filters':     filters,
            'PaginationConfig': {'MaxRecords': limit}
        }
    )

    rv = []
    for reservation in instance_data:
        for instance in reservation['Instances']:
            rv.append(instance)

    return rv

# -{CLI Commands}------------------------------------------------------------------------------------------------------#

@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@pass_context
def subcmd(context, profile, verbose, debug):
    """EC2 commands was created to help manage AWS EC2 Snapshots."""
    context.obj['aws_profile'] = profile
    context.verbose = verbose
    context.debug = debug


@subcmd.command()
@click.option('--cidr-to-copy-from', default=None, help='CIDR block of existing rule to copy from.')
@click.option('--cidr-to-add', default=None, help='The CIDR block to whitelist.')
@pass_context
def duplicate_whitelisting_by_cidr(ctx, cidr_to_copy_from, cidr_to_add):
    """
    :param ctx:
    :param limit:
    :param filters:
    :param output:
    :return:
    """
    log_prefix = '[duplicate_whitelisting_by_cidr]'.format()
    ctx.vlog('{}::[started]'.format(log_prefix))
    ctx.vlog('{}::[cidr_to_copy_from]::[{}]'.format(log_prefix, str(cidr_to_copy_from)))
    ctx.vlog('{}::[cidr_to_add]::[{}]'.format(log_prefix, str(cidr_to_add)))

    ec2_client = ctx.get_aws_client('ec2')

    sec_groups = get_security_groups_by_filters(ctx, [{'Name': 'ip-permission.cidr', 'Values': [cidr_to_copy_from]}])
    for sec_group in sec_groups:
        new_rules = []
        existing_rule = []
        if 'IpPermissions' in sec_group:
            for ip_perm in sec_group['IpPermissions']:
                if 'IpRanges' in ip_perm:
                    for range in ip_perm['IpRanges']:
                        if range['CidrIp'] == cidr_to_add:
                            existing_rule.append(ip_perm)

                        if range['CidrIp'] == cidr_to_copy_from:
                            new_range = copy.copy(range)
                            new_range['CidrIp'] = cidr_to_add
                            new_range['Description'] = 'replacement rule'
                            new_rule = copy.copy(ip_perm)
                            new_rule['IpRanges']    = [new_range]
                            new_rule['UserIdGroupPairs']    = []
                            new_rule['Ipv6Ranges']          = []
                            new_rule['PrefixListIds']       = []

                            new_rules.append(new_rule)

        if not existing_rule:
            try:
                ctx.vlog('{}::[update]::[new_rules]::[{}]::[{}]'.format(log_prefix, sec_group['GroupId'], new_rules))
                ec2_client.authorize_security_group_ingress(GroupId=sec_group['GroupId'], IpPermissions=new_rules)
            except botocore.exceptions.ClientError as e:
                ctx.vlog('{}::[api error]::[{}]::[{}]::[{}]'.format(
                    log_prefix, 'authorize_security_group_ingress',
                    e.response['Error']['Code'], e.response['Error']['Message'])
                )
                debug_exit('error latest')

        else:
            ctx.dlog('{}::[no update]::[existing_rules]::[{}]::[{}]'.format(log_prefix, sec_group['GroupId'], existing_rule))


    ctx.vlog('{}::[completed]'.format(log_prefix))


@subcmd.command()
@click.option('--limit', default=1, help='limit the number of instances.')
@click.option('--filters', default=None, type=click.Path(exists=True, file_okay=True, dir_okay=False), help='Provide filters to limit EC2 search.')
@click.option('--output', default='-',  help='Path for json output. (truncate mode)', type=click.File(mode='w+'))
@pass_context
def describe_instances(ctx, limit, filters, output):
    log_prefix = '[describe_instances]'.format()
    ctx.vlog('{}::[started]'.format(log_prefix))
    ctx.vlog('{}::[limit]::[{}]'.format(log_prefix, str(limit)))
    ctx.vlog('{}::[aws_profile]::[{}]'.format(log_prefix, str(ctx.obj['aws_profile'])))
    ctx.vlog('{}::[output]::[{}]'.format(log_prefix, str(output)))

    filters_search  = None

    if filters:
        filters_file    = click.open_file(filters, 'r')
        filters_data    = yaml.safe_load(filters_file)

        if 'filters' in filters_data:
            filters_search = filters_data['filters']

        if 'limit' in filters_data:
            limit = filters_data['limit']

    ctx.obj['instances']    = describeInstances(ctx, limit, filters_search)
    ctx.vlog('{}::[instances found]::[{}]'.format(log_prefix, str(len(ctx.obj['instances']))))
    ctx.vlog('{}::[filters_search]::[{}]'.format(log_prefix, str(filters_search)))
    ctx.vlog('{}::[limit]::[{}]'.format(log_prefix, str(limit)))

    if output is not None:
        json.dump(ctx.obj['instances'], output, default=str)
        output.write(",\n")

    ctx.vlog('{}::[completed]'.format(log_prefix))


@subcmd.command()
@click.option('--ssh_key_dir', envvar='SSH_KEY_DIR', default='data/ssh-keys', help='Dir containing ssh keys to use', type=click.Path(exists=True, file_okay=False))
@pass_context
def describe_ssh_key(ctx, ssh_key_dir):
    log_prefix = '[describe_ssh_key]'.format()
    ctx.vlog('{}::[started]'.format(log_prefix))
    ctx.obj['ssh_keys'] = describeSshKeys(ssh_key_dir)
    ctx.vlog('{}::[num keys found]::[{}]'.format(log_prefix, str(len(ctx.obj['ssh_keys']))))
    ctx.dlog('{}::[keys found]::[{}]'.format(log_prefix, ctx.obj['ssh_keys']))
    ctx.vlog('{}::[completed]'.format(log_prefix))


@subcmd.command()
@click.option('--limit', default=1000, help='limit the number of instances.')
@click.option('--filters', default=None, type=click.Path(exists=True, file_okay=True, dir_okay=False), help='Provide filters to limit EC2 search.')
@click.option('--output', default='-',  help='Path for json output. (truncate mode)', type=click.File(mode='w+'))
@click.option('--ssh_key_dir', default='data/ssh-keys', help='Dir containing ssh keys to use', type=click.Path(exists=True, file_okay=False))
@click.option('--test_all_ssh', is_flag=True, default=False, help='Forces a test of all ssh keys and users.')
@pass_context
def generate_instance_data(ctx, limit, filters, output, ssh_key_dir, test_all_ssh):
    log_prefix = '[generate_instance_data]'.format()
    ctx.vlog('{}::[started]'.format(log_prefix))
    ctx.vlog('{}::[limit]::[{}]'.format(log_prefix, str(limit)))
    ctx.vlog('{}::[output]::[{}]'.format(log_prefix, str(output.name)))
    ctx.vlog('{}::[ssh_key_dir]::[{}]'.format(log_prefix, str(ssh_key_dir)))
    ctx.vlog('{}::[test_all_ssh]::[{}]'.format(log_prefix, str(test_all_ssh)))

    ctx_local = click.get_current_context()
    ctx_local.invoke(describe_ssh_key, ssh_key_dir = ssh_key_dir)
    ctx_local.invoke(describe_instances, limit = limit, filters = filters, output = None)

    instances           = ctx.obj['instances']
    ssh_keys            = ctx.obj['ssh_keys']
    tested_instances    = []
    break_on_preferred  = False if test_all_ssh is True else True

    output.write('[')
    with click.progressbar(instances, label='{}::[Building instance data]'.format(log_prefix)) as instance_bar:
        for instance in instance_bar:
            if 'PublicIpAddress' in instance and instance['PublicIpAddress'] != '':
                instance   = testInstanceSshKeys(ctx, instance, ssh_keys, break_on_preferred = break_on_preferred)
                tested_instances.append(instance)
                json.dump(instance, output, default=str)
                if not instance is instances[-1]:
                    output.write(',')
    output.write(']')
    output.close()
    ctx.vlog('{}::[num_instances_found]::[{}]'.format(log_prefix, str(len(tested_instances))))
    ctx.vlog('{}::[num_instances_total]::[{}]'.format(log_prefix, str(len(instances))))
    ctx.vlog('{}::[completed]'.format(log_prefix))


@subcmd.command()
@click.option('--plan', default=None, type=click.Path(exists=True, file_okay=True, dir_okay=False), help='Path to a valid plan yaml file; which defines plan actions (upload|execute).')
@click.option('--filters', default=None, type=click.Path(exists=True, file_okay=True, dir_okay=False), help='Path to a valid filters yaml file; which defines the AWS EC2 filters to run plans against specific targets.')
@click.option('--output', default='-',  help='Path to output the results of the plan actions, in CSV format. (Default: stdout). It\'s a good idea to send these to a log file for tracking of runs.')
@click.option('--rebuild_cache', is_flag=True, default=False, help='Pass this option flag to force the instance cache data to refresh (may take a while for large result sets.')
@click.option('--cache_ttl', default=600, type=click.INT, help='Set the timeout, in seconds, for how long the EC2 cached data should retained before downloading a new one based on the targets.')
@pass_context
def run_plan(ctx, plan, filters, output, rebuild_cache, cache_ttl):
    """
        This command is used to run plans against one or more EC2 instances. A plan can consist of uploading 
        one or more files and running one or more commands, per EC2 instance. You can define a custom filter, 
        in a yaml file, to specify your targets to run a plan against.

        Running a plan requires us to find all matching target EC2 descriptions and then find a valid ssh 
        key for each one. We do this to ensure we can run a plan against a given instance without worrying 
        about custom ssh keys for each one, just place valid ones in `data/ssh-keys` and any *.priv keys 
        will be used to test for ssh access. Due to this requirement of a cached file we have a `--cache_ttl` 
        option with a Default of 43200 seconds (1 Day), you can override that with the `--cache_ttl` option 
        to modify the timeout or you can force it to rebuild by passing the `--rebuild_cache` option.
    """
    log_prefix = '[god_mode]'.format()
    ctx.vlog('{}::[started]'.format(log_prefix))
    ctx.vlog('{}::[plan]::[{}]'.format(log_prefix, str(plan)))
    ctx.vlog('{}::[filters]::[{}]'.format(log_prefix, str(filters)))
    ctx.vlog('{}::[output]::[{}]'.format(log_prefix, str(output)))
    cached_instance_file    = 'data/cache/ec2-filters--{}.json'.format(click.format_filename(filters, True).replace('.yml', ''))
    fh                      = Path(cached_instance_file)

    if output is '-':
        output  = click.open_file(output, 'w+')
    else:
        output = click.open_file(output, 'a+')

    try:
        fh_stat = fh.stat()

        # Delete the cached file if it's empty; likely exception caused a failed run.
        if os.path.getsize(cached_instance_file) == 0:
            os.remove(cached_instance_file)
            ctx.log('{}::[no instances found]::[cached_instance_file]::[{}]'.format(log_prefix, cached_instance_file))
            #raise Exception('{}::[cached_instance_file]::[empty]::[{}]'.format(log_prefix, cached_instance_file))
            rebuild_cache = True
            fh = Path(cached_instance_file)
            fh_stat = fh.stat()

    # create new cache file
    except FileNotFoundError:
        ctx.vlog('{}::[cached_instance_file]::[does not exist]::[{}]'.format(log_prefix, str(cached_instance_file)))
        rebuild_cache = True

    # use or rebuild cache file.
    else:
        ctx.vlog('{}::[cached_instance_file]::[does exist]::[{}]'.format(log_prefix, str(cached_instance_file)))
        time_now        = datetime.utcnow()
        time_fh         = datetime.utcfromtimestamp(fh_stat.st_mtime)
        difference      = time_now - time_fh

        if difference.seconds > cache_ttl or rebuild_cache is True:
            ctx.vlog('{}::[cached_instance_file]::[rebuilding cache ({}) seconds old]::[{}]'.format(log_prefix, str(difference.seconds), str(cached_instance_file)))
            import shutil
            rebuild_cache = True
            file_from   = cached_instance_file
            file_to     = '{}-expired_by-{}'.format(cached_instance_file, ctx.uuid)

            ctx.vlog('{}::[cached_instance_file]::[moving]::[{}]::[to]::[{}]'.format(log_prefix, str(file_from), str(file_to)))
            shutil.move(file_from, file_to)

    if rebuild_cache is True:
        fopen = click.open_file(cached_instance_file, 'w')
        ctx_local = click.get_current_context()
        ctx_local.invoke(generate_instance_data, filters = filters, output = fopen)

    try:
        if plan is not None:
            plan_file           = click.open_file(plan, 'r')
            plan_data           = yaml.safe_load(plan_file)
    except FileNotFoundError as error:
        raise Exception('{}::[plan_file]::[not found]::[{}]::[{}]'.format(log_prefix, str(plan_file), error))

    try:
        instance_data_file  = click.open_file(cached_instance_file, 'r')
        ctx.vlog('{}'.format(instance_data_file))
        instance_data_json  = json.load(instance_data_file)
        ctx.vlog('{}::[number_instances_found]::[{}]'.format(log_prefix, str(len(instance_data_json))))
    except FileNotFoundError as error:
        raise Exception('{}::[cached_instance_file]::[not found]::[{}]::[{}]'.format(log_prefix, str(cached_instance_file), error))

    try:
        results = connectionGroupRun(ctx, buildConnectionsFromInstanceData(ctx, instance_data_json), plan_data)
    except:
        raise Exception('{}::[connectionGroupRun]::[error found]::[{}]'.format(log_prefix, str(cached_instance_file)))

    # default is csv format for output. adding meta data for longer tracking.
    output.write('{},{},{},'.format(plan,cached_instance_file,datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC')))
    json.dump(results, output, default=str)
    output.write(",\n")
    ctx.vlog('{}::[num results]::[{}]'.format(log_prefix, str(len(results))))
    ctx.vlog('{}::[completed]'.format(log_prefix))


@subcmd.command()
@click.option('--filters', default=None, type=click.Path(exists=True, file_okay=True, dir_okay=False), help='Path to a valid filters yaml file; which defines the AWS EC2 filters to run plans against specific targets.')
@click.option('--output', default='-',  help='Path to output the results of the plan actions, in CSV format. (Default: stdout). It\'s a good idea to send these to a log file for tracking of runs.')
@click.option('--rebuild_cache', is_flag=True, default=False, help='Pass this option flag to force the instance cache data to refresh (may take a while for large result sets.')
@click.option('--cache_ttl', default=600, type=click.INT, help='Set the timeout, in seconds, for how long the EC2 cached data should retained before downloading a new one based on the targets.')
@pass_context
def get_ips(ctx, filters, output, rebuild_cache, cache_ttl):
    """
    This command serves to return json for each instance founnd in the filters; it's main use is
    to confirm filters are working as desired before running a large set or gathering active data if desired.
    :param ctx:
    :param filters:
    :param output:
    :param rebuild_cache:
    :param cache_ttl:
    :param no_output_items:
    :return:
    """
    log_prefix = '[get-ips]'.format()
    ctx.vlog('{}::[started]'.format(log_prefix))

    filters_search  = None

    if filters:
        filters_file    = click.open_file(filters, 'r')
        filters_data    = yaml.safe_load(filters_file)

        if 'filters' in filters_data:
            filters_search = filters_data['filters']

        if 'limit' in filters_data:
            limit = filters_data['limit']

    instances = describeInstances(ctx, limit, filters_search)

    if instances:
        print('{}\t{}\t{}\t{}\t{}'.format('Name', 'InstanceId', 'PublicDnsName', 'PublicIpAddress', 'PrivateIpAddress'))

    for instance in instances:
        name = instance['InstanceId']
        if 'Tags' in instance:
            for tag in instance['Tags']:
                if tag['Key'].lower() == 'name':
                    name = tag['Value']
                    break

        print('{}\t{}\t{}\t{}\t{}'.format(name, instance['InstanceId'], instance['PublicDnsName'], instance['PublicIpAddress'], instance['PrivateIpAddress']))

    ctx.vlog('{}::[instances found]::[{}]'.format(log_prefix, len(instances)))
    ctx.dlog('{}::[instances]::[{}]'.format(log_prefix, instances))
    ctx.vlog('{}::[finished]'.format(log_prefix))

