#!/usr/bin/env python
"""
This file must be a copy from cli.py, with the custom import needed for lambda functionality.
This is less than ideal, so a big nice fun todo will be to address the environment issues
by consolidating them and using a more standard python praccalltice; here we just make a work around,
for the work around we already made.
"""

import sys
import os
import json
import pickle
import hashlib

#CONTEXT_SETTINGS = dict(auto_envvar_prefix='COMPLEX')
# Hard coding condition for self hosted packages.
if os.path.exists("/opt/ops-cli.deploy/bin/vendor/lib/python3.7/site-packages"):
    sys.path.append("/opt/ops-cli.deploy/bin/vendor/lib/python3.7/site-packages")

import click
import uuid
from datetime import datetime
import boto3
import botocore
from pathlib import Path

#-{sourced from: cli.py}------------------------------------------------#

class Context(object):
    obj = {}

    def __init__(self):
        self.verbose    = False
        self.debug      = False
        self.home       = os.getcwd()
        self.uuid        = '{}'.format(uuid.uuid4())

    def log(self, msg, *args):

        """Logs a message to stderr."""
        if args:
            msg %= args
        click.echo('[{}]::[{}]::{}'.format(self.uuid, datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S UTC'), msg), file=sys.stderr)

    def vlog(self, msg, *args):
        """Logs a message to stderr only if verbose is enabled."""
        if self.verbose:
            self.log(msg, *args)

    def dlog(self, msg, *args):
        """Logs a message to stderr only if debug is enabled."""
        if self.debug:
            self.log(msg, *args)

    def get_uuid(self):
        return self.uuid

    def get_aws_client(self, client_name = "ec2", region = None):
        client_namespace = format('client_{}_{}'.format(client_name, region))
        self.dlog('[get_aws_client]::[client_namespace]::[{}]'.format(client_namespace))

        if client_namespace in self.obj:
            self.dlog('[get_aws_client]::[using existing client]::[{}]'.format(client_namespace))
            client = self.obj[client_namespace]
        else:
            self.dlog('[get_aws_client]::[create new client]::[{}]'.format(client_namespace))
            session = self.get_aws_session(region)

            if not region:
                region  = self.obj['region']

            client_namespace            = format('client_{}_{}'.format(client_name, region))
            client                      = session.client(client_name, region)
            self.obj[client_namespace]  = client

        return client

    def get_aws_session(self, region=None):
        self.dlog('[get_aws_session]::[region]::[{}]'.format(region))

        if 'session' in self.obj and self.obj['session'] is not None:
            self.dlog('[get_aws_session]::[using existing session]')
            session = self.obj['session']
        elif self.obj['aws_profile'] != "":
            self.dlog('[get_aws_session]::[starting session]::[with profile]::[{}]'.format(self.obj['aws_profile']))
            session = boto3.session.Session(profile_name=self.obj['aws_profile'], region_name=region)
            # TODO: remove if no issue when using with region defined in profile.
            # if region:
            #     session = boto3.session.Session(profile_name=self.obj['aws_profile'], region_name=region)
            # else:
            #     session = boto3.session.Session(profile_name=self.obj['aws_profile'])
        else:
            self.dlog('[get_aws_session]::[starting session]::[no profile]')
            session = boto3.session.Session()

        # define a session namespace to allow cache to be unique per iam/region/account.
        client = session.client('sts')
        caller_id = client.get_caller_identity()
        caller_id.pop('ResponseMetadata', None)
        caller_id['region']             = session.region_name
        self.obj['region']              = session.region_name
        self.obj['session']             = session
        self.obj['caller_id']           = caller_id
        self.obj['session_namespace']   = hashlib.md5(str(pickle.dumps(caller_id)).encode("utf-8")).hexdigest()

        self.dlog('[get_aws_session]::[region]::[{}]'.format(self.obj['region']))

        return session

    def get_from_aws_api(self, api_namespace, api_name, api_response_key, api_request_config, api_cache_ttl = 0, region = ''):
        client              = self.get_aws_client(api_namespace, region)
        use_cache           = True if api_cache_ttl > 0 else False

        # namespace calculated for each api cache request.
        call_ns = 'aws.{}.{}'.format(
            hashlib.md5('.'.join([self.obj['session_namespace'], api_namespace, region, api_name, str(api_response_key)]).encode('utf-8')).hexdigest(),
            hashlib.md5(str(pickle.dumps(api_request_config)).encode("utf-8")).hexdigest()
        )

        log_prefix  = '[get_from_aws_api]::[{}]'.format(call_ns)
        self.dlog('{}::[started]'.format(log_prefix))
        self.dlog('{}::[api_request_config]::[{}]::[use_cache]::[{}]'.format(log_prefix, api_request_config, use_cache))

        check_cache = self.get_cache(call_ns, None, api_cache_ttl)
        if use_cache is True and check_cache is not None:
            self.dlog('{}::[completed]::[cache used]'.format(log_prefix))
            return check_cache

        results = []
        if 'PaginationConfig' in api_request_config:
            paginator           = client.get_paginator(api_name)
            iterator            = paginator.paginate(**api_request_config)
            count               = 0

            self.vlog('{}::[call-api]'.format(log_prefix))
            for page in iterator:
                count += 1
                self.dlog('{}::[item]::[{}]'.format(log_prefix, count))
                if api_response_key:
                    if api_response_key not in page:
                        self.dlog('{}'.format(page))
                        raise Exception('{}::[response_key]::[{}]::[not in]::[paginated response]::[{}]'.format(log_prefix, api_response_key, api_name))
                    for item in page[api_response_key]:
                        results.append(item)
                else:
                    for item in page:
                        results.append(item)
        else:
            try:
                func = getattr(client, api_name)
                response = func(**api_request_config)

                if api_response_key:
                    if api_response_key not in response:
                        self.dlog('{}'.format(response))
                        raise Exception('{}::[response_key]::[{}]::[not in]::[response]::[{}]'.format(log_prefix, api_response_key, api_name))
                    for item in response[api_response_key]:
                        results.append(item)
                else:
                    results = response

            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "404":
                    return None
                else:
                    self.dlog('{}::[api error]::[{}]::[{}]::[{}]'.format(log_prefix, api_name, e.response['Error']['Code'], e.response['Error']['Message']))
                    raise e

        self.vlog('{}::[completed]'.format(log_prefix))
        return self.put_cache(call_ns, results)

    def put_cache(self, name_space, results, fo_mode = 'w'):

        if not isinstance(name_space, str) or len(name_space) > 265:
            self.dlog('[put_cache]::[cache-error]::[{}]'.format(name_space))
            raise Exception('[put_cache]::[name_space]::[incorrect type/length]::[{}]::[{}]'.format(isinstance(name_space, str), len(name_space)))
        elif isinstance(name_space, list) and len(name_space) == 0:
            self.dlog('[put_cache]::[cache-missed]::[{}]'.format(name_space))
            return results
        else:
            cache_file = 'data/cache/{}.json'.format(name_space)
            try:
                fopen = click.open_file(cache_file, fo_mode)
                json.dump(results, fopen, default=str)
                if fo_mode == 'a':
                    fopen.write("\n")
                self.dlog('[put_cache]::[cache-saved]::[{}]'.format(cache_file))
            except Exception as e:
                self.dlog('[failed to create cached file]::[{}]::[{}]'.format(cache_file, e))

            return results


    def get_cache(self, name_space, default_return = None, cache_ttl = 0, rebuild_cache = False):
        cache_file = 'data/cache/{}.json'.format(name_space)

        try:
            fh = Path(cache_file)
            fh_stat = fh.stat()

            if os.path.getsize(cache_file) == 0:
                os.remove(cache_file)

        # create new cache file
        except FileNotFoundError:
            self.dlog('[get_cache]::[cache-missed]::[{}]'.format(cache_file))
            return default_return

        # use or rebuild cache file.
        else:
            time_now = datetime.utcnow()
            time_fh = datetime.utcfromtimestamp(fh_stat.st_mtime)
            difference = time_now - time_fh
            if difference.seconds > cache_ttl or rebuild_cache is True:
                self.dlog('[get_cache]::[cache-expired]::[{}]::[{}>{}]'.format(cache_file, difference, cache_ttl))
                import shutil
                file_from   = cache_file
                file_to     = '{}-expired_by-{}'.format(cache_file, self.uuid)
                shutil.move(file_from, file_to)
                return default_return

            self.dlog('[get_cache]::[cache-hit]::[{}]::[{}<{}]'.format(cache_file, difference, cache_ttl))
            return json.load(click.open_file(cache_file, 'r'))

pass_context   = click.make_pass_decorator(Context, ensure=True)
command_dir    = os.path.join(os.path.dirname(__file__), 'command')

# @todo context isn't being passed, please find out why and when fixed add back in verbose|debug options
class AwsToolsCLI(click.MultiCommand):

    def list_commands(self, ctx):
        rv  = []
        for filename in os.listdir(command_dir):
            if filename.endswith('.py') and filename.startswith('cmd_'):
                rv.append(filename[4:-3])
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        ns  = {}
        fn  = os.path.join(command_dir, 'cmd_' + name + '.py')

        if not os.path.isfile(fn):
            return None

        with open(fn) as f:
            code = compile(f.read(), fn, 'exec')
            eval(code, ns, ns)
        return ns['subcmd']

@click.command(cls = AwsToolsCLI, help = '')
def cli():
    pass

if __name__ == '__main__':
    cli()