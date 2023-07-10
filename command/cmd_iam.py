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
from dataclasses import dataclass, field
from collections import OrderedDict, abc
from datetime import datetime
from dateutil import parser
import csv

#-{Command Function/Classes}-------------------------------------------------------------------------------------------#

def debug_exit(o):
    debug_output(o)
    sys.exit()

def debug_output(o):
    print(json.dumps(o, indent=4, sort_keys=True, default=str))

class DataCollection(object):
    data: dict = {}

    def __init__(self, data):
        self.data = data

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index]

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def values(self):
        return self.data.values()

    def set(self, index, item):
        self.data[index] = item


class RoleCollection(DataCollection):
    def __init__(self, context, limit=999999, region=''):
        self.context = context
        self.region = region
        data = {}
        resources = self.context.get_from_aws_api(
            api_namespace='iam', api_name='list_roles', api_response_key='Roles', api_cache_ttl=9999999999,
            api_request_config={'PaginationConfig': {'MaxItems': limit}}, region=self.region
        )
        for item in resources:
            item.update(self.get_role(item['RoleName']))    # RoleLastUsed data inconsistent in list api still.
            data[item['RoleId']] = Role(**item)

        DataCollection.__init__(self, data)

    def get_role(self, role_name):
        try:
            return self.context.get_from_aws_api(
                api_namespace='iam', api_name='get_role', api_response_key='Role', api_cache_ttl=9999999999,
                api_request_config={'RoleName': role_name}, region=self.region
            )
        except Exception as e:
            return {}

    def output(self):
        print('')
        print('[CSV OUTPUT]===========================================================================================')
        data = csv.DictWriter(sys.stdout, ['Name', 'Description', 'DateCreated', 'DateLastUsed', 'RegionLastUsed'])
        data.writeheader()
        for id,role in self.items():
            wr = csv.writer(sys.stdout, quoting=csv.QUOTE_ALL)
            row = [
                role.RoleName,
                role.Description,
                role.CreateDate,
                role.RoleLastUsed['LastUsedDate'] if 'LastUsedDate' in role.RoleLastUsed else None,
                role.RoleLastUsed['Region'] if 'Region' in role.RoleLastUsed else None
            ]
            wr.writerow(row)
        print('=======================================================================================================')
        print('')


@dataclass
class Role:
    MaxSessionDuration: int
    Path: str = ""
    RoleName: str = ""
    RoleId: str = ""
    Arn: str = ""
    CreateDate: str = ""
    AssumeRolePolicyDocument: str = ""
    Description: str = ""
    PermissionsBoundary: dict = field(default_factory=dict)
    Tags: dict = field(default_factory=dict)
    RoleLastUsed: dict = field(default_factory=dict)

    def asadict(self):
        return {
            'RoleName': self.RoleName,
            'Description': self.Description,
            'CreateDate': self.CreateDate,
            'RoleLastUsed': self.RoleLastUsed
        }

#-{CLI Commands}-------------------------------------------------------------------------------------------------------#

@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@pass_context
def subcmd(context, profile, verbose, debug):
    """does stuff for you."""
    context.obj['aws_profile']  = profile
    context.verbose             = verbose
    context.debug               = debug
    context.dlog('[{}].[{}].[{}]'.format(profile, verbose, debug))

@subcmd.command()
@click.option('-l', '--limit', envvar='LIMIT', default=99999, help='Define Limit')
@pass_context
def list_roles(context, limit):
    log_prefix = "list_roles"
    context.dlog('[{}]::[started]::[]'.format(log_prefix))
    RoleCollection(context=context, limit=limit).output()
    context.dlog('[{}]::[completed]::[]'.format(log_prefix))


