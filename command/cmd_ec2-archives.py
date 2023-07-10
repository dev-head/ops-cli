import click
from cli import pass_context

# -{Import unique to this command}--------------------------------------------------------------------------------------#
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


# -{Command Function/Classes}-------------------------------------------------------------------------------------------#

def validate_input(value):
    if value.lower() == 'exit' or value.lower() == 'quit':
        print('\n\n')
        print('{-------------------------}  ')
        print('{----[This is the way]----}  ')
        print('{-------------------------}  ')
        sys.exit()
    return value


def get_input(value, default_value=None):
    return validate_input(click.prompt(value, default=default_value))


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


# -{CLI Commands}-------------------------------------------------------------------------------------------------------#

@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@click.option('-y', '--dry-run', envvar='DRY_RUN', is_flag=True, default=False, help='Enables a Dry run (no changes)')
@click.option('--cache-ttl', envvar='CACHETTL', default="9999999999", help='Optionally set local API cache result ttl (Default: 9999999999')
@pass_context
def subcmd(context, profile, verbose, debug, dry_run, cache_ttl):
    """EC2 Archives command was created to help manage AWS EC2 Snapshots."""
    context.obj['aws_profile'] = profile
    context.verbose = verbose
    context.debug = debug
    context.dry_run = dry_run
    context.cache_ttl = int(cache_ttl)

    context.dlog('[{}].[{}].[{}].[{}].[{}]'.format(profile, verbose, debug, dry_run, cache_ttl))


# @todo inver the `interactive` logic to ensure it's the default.
@subcmd.command()
@click.option('--name', default='', help='Name filter used to match against snapshots targeted. Supports regex as well. Example: "^(.)Example(?i)"')
@click.option('--delete_older_than_date', default='', help='Remove all snapshots older than this date. Example: [2022-01-03 06:00:42.001000+00:00]')
@click.option('--retain_newer_than_date', default='', help='Retain all snapshots newer than this date. Example: [2022-01-03 06:00:42.001000+00:00]')
@click.option('--retain_oldest', is_flag=True, default=False, help='Retain the oldest snapshot.')
@click.option('--retain_newest', is_flag=True, default=False, help='Retain the newest snapshot.')
@click.option('--retain_eol', is_flag=True, default=False, help='Retain any EOL (End of life) snapshots.')
@click.option('--interactive', is_flag=True, default=False, help='No action taken until approved.')
@click.option('--suppress_output', is_flag=True, default=False, help='Optional to prevent the full target list.')
@click.option('--limit', default=999999999, help='Optional limit of snapshots to delete, helps for debugging.')
@pass_context
def purge_snapshots(context, name, delete_older_than_date, retain_newer_than_date, retain_oldest, retain_newest,
                    retain_eol, interactive, suppress_output, limit):
    """
        EC2 Archives :: purge_snapshots command was created to identify and purge AWS EC2 Snapshots.
        There are newer built in tools that support managing EC2 Snapshots, those should be considered before using this.
        This command is designed to safely attempt to categorize and retain based on user supplied filters; this is
        most useful when amd if the need arises to clear out unmanaged EC2 Snapshots, or at least view them with some
        stronger logic to help determine if they should be deleted or not.
    """

    log_prefix = "purge-snapshots"
    context.dlog('[{}]::[started]::[]'.format(log_prefix))

    if context.dry_run:
        context.dlog('[{}]::[dry_run]::[{}]'.format(log_prefix, context.dry_run))

    rules = {
        'name': name,
        'delete_older_than_date': delete_older_than_date,
        'retain_newer_than_date': retain_newer_than_date,
        'retain_oldest': retain_oldest,
        'retain_newest': retain_newest,
        'retain_eol': retain_eol,
        'interactive': interactive,
        'suppress_output': suppress_output,
        'limit': limit
    }

    court = AdjudicateSnapshotGroups(context=context, rules=rules)

    # output for visual review as needed.
    if not suppress_output:
        cnt_deleted = 0
        cnt_retained = 0

        for snapshot in court.get_judged():
            if snapshot.LifeCycle['actionSuggested'] == 'retain':
                cnt_retained += 1

            elif snapshot.LifeCycle['actionSuggested'] == 'remove':
                cnt_deleted += 1

            context.log('{}::[{}]:[{}]::[reasons]::[{}]'.format(snapshot.NameTag, snapshot.SnapshotId, snapshot.LifeCycle['actionSuggested'], ', '.join(snapshot.LifeCycle['actionReasons'])))

    if interactive:
        print('')
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
        print('Based on these rules...')
        debug_output(rules)
        print('')
        print('We found [{}] snapshots to delete and [{}] snapshots to retain out of [{}] total snapshots.'.format(cnt_deleted, cnt_retained, (cnt_deleted + cnt_retained)))
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
        user_approved = get_input('Do you want to delete these EC2 Snapshots?(Y/N)', 'N')
        if user_approved.lower() == 'y':
            debug_output('okay..removing now please stay tuned, this will take a while.')
        else:
            print('Good Bye')
            context.dlog('[{}]::[started]::[]'.format(log_prefix))
            return

    cnt_deleted = 0
    cnt_retained = 0
    for snapshot in court.get_judged():
        context.dlog('{}::[{}]:[{}]::[reasons]::[{}]'.format(snapshot.NameTag, snapshot.SnapshotId, snapshot.LifeCycle['actionSuggested'], ', '.join(snapshot.LifeCycle['actionReasons'])))

        if snapshot.LifeCycle['actionSuggested'] == 'retain':
            cnt_retained += 1
            continue

        if snapshot.LifeCycle['actionSuggested'] == 'remove':
            if context.dry_run:
                context.log('[DRY RUN::REMOVE]::{}::[{}]:[{}]::[{}]'.format(snapshot.NameTag, snapshot.SnapshotId, snapshot.LifeCycle['actionSuggested'], ', '.join(snapshot.LifeCycle['actionReasons'])))
            else:
                if cnt_deleted < limit:
                    try:
                        context.get_from_aws_api(api_namespace='ec2', api_name='delete_snapshot', api_response_key='',
                                                 api_cache_ttl=0, api_request_config={'SnapshotId': snapshot.SnapshotId})
                    except BaseException as err:
                        context.log('Failed to delete snapshot]::[{}]::[because]::[{}]'.format(snapshot.SnapshotId, err))
                        pass
                    context.log('[REMOVED]::{}::[{}]:[{}]::[{}]'.format(snapshot.NameTag, snapshot.SnapshotId, snapshot.LifeCycle['actionSuggested'],', '.join(snapshot.LifeCycle['actionReasons'])))

        cnt_deleted += 1

    print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
    print('Based on these rules...')
    debug_output(rules)
    print('')
    print('We deleted [{}] snapshots to and retained [{}] snapshots out of [{}] total snapshots.'.format(cnt_deleted, cnt_retained, (cnt_deleted + cnt_retained)))
    print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
    print('')

    context.vlog('[deleted]::[{}]::[retained]::[{}]'.format(cnt_deleted, cnt_retained))
    context.dlog('[{}]::[completed]'.format(log_prefix))


# @todo eol_strings should be more expressive as a regex, but for current use a string match is all that's needed.
class AdjudicateSnapshotGroups():
    judged: list = []
    eol_strings: list = []

    def __init__(self, context, rules, eol_strings=['eol', 'final']):
        self.rules = rules
        self.eol_strings = eol_strings
        self.snap_data = SnapshotData(context=context)
        self.grouped_snapshots = GroupedSnapshots(snapshots=self.snap_data.snapshots)
        self.begin_trial()

    def get_judged(self):
        return self.judged

    def begin_trial(self):
        for group, snapshots in self.grouped_snapshots.items():
            if not self.group_allowed(group):
                continue

            self.find_older_than_date(snapshots)
            self.find_newer_than_date(snapshots)
            self.find_eol(snapshots)

            available_inventory = self.get_available_inventory(snapshots)   # must be post date filter consideration.
            num_snaps_avail = len(available_inventory)
            self.find_oldest(available_inventory if num_snaps_avail else snapshots)
            self.find_newest(available_inventory if num_snaps_avail else snapshots)

            # lets judge them.
            for snapshot in snapshots:

                if snapshot.LifeCycle['isEol']:
                    snapshot.LifeCycle['actionSuggested'] = 'retain'
                    snapshot.LifeCycle['actionReasons'].append('Snapshot is EOL')
                    self.judged.append(snapshot)
                    continue

                if snapshot.LifeCycle['isOldest'] or snapshot.LifeCycle['isNewest']:
                    if snapshot.LifeCycle['isNewest']:
                        snapshot.LifeCycle['actionSuggested'] = 'retain'
                        snapshot.LifeCycle['actionReasons'].append('Snapshot is the newest')

                    if snapshot.LifeCycle['isOldest']:
                        snapshot.LifeCycle['actionSuggested'] = 'retain'
                        snapshot.LifeCycle['actionReasons'].append('Snapshot is the oldest')
                    self.judged.append(snapshot)
                    continue

                if snapshot.LifeCycle['isOlderThanDesiredDate']:
                    snapshot.LifeCycle['actionSuggested'] = 'remove'
                    snapshot.LifeCycle['actionReasons'].append('Snapshot is older than desired')
                    self.judged.append(snapshot)
                    continue

                if snapshot.LifeCycle['isNewerThanDesiredDate']:
                    snapshot.LifeCycle['actionSuggested'] = 'retain'
                    snapshot.LifeCycle['actionReasons'].append('Snapshot is newer than desired')
                    self.judged.append(snapshot)
                    continue

                snapshot.LifeCycle['actionSuggested'] = 'remove'
                snapshot.LifeCycle['actionReasons'].append('Not otherwise retained')
                self.judged.append(snapshot)

    def find_older_than_date(self, snapshots):
        date_check = self.get_rule('delete_older_than_date')
        if date_check:
            date_check = self.get_timestamp(date_check)
            for snapshot in snapshots:
                if self.get_timestamp(snapshot.StartTime) < date_check:
                    snapshot.LifeCycle['isOlderThanDesiredDate'] = True

    def find_newer_than_date(self, snapshots):
        date_check = self.get_rule('retain_newer_than_date')
        if date_check:
            date_check = self.get_timestamp(date_check)
            for snapshot in snapshots:
                if self.get_timestamp(snapshot.StartTime) > date_check:
                    snapshot.LifeCycle['isNewerThanDesiredDate'] = True

    def find_eol(self, snapshots):
        if self.get_rule('retain_eol'):
            for snapshot in snapshots:
                for eol_string in self.eol_strings:
                    if eol_string in snapshot.Description.lower() or eol_string in snapshot.NameTag.lower():
                        snapshot.LifeCycle['isEol'] = True

    def find_oldest(self, snapshots):
        if self.get_rule('retain_oldest'):
            snap = min(snapshots, key=lambda snapshot: self.get_timestamp(snapshot.StartTime))
            snap.LifeCycle['isOldest'] = True

    def find_newest(self, snapshots):
        if self.get_rule('retain_newest'):
            snap = max(snapshots, key=lambda snapshot: self.get_timestamp(snapshot.StartTime))
            snap.LifeCycle['isNewest'] = True

    def get_available_inventory(self, snapshots):
        inventory = []
        for snapshot in snapshots:
            if snapshot.LifeCycle['isNewerThanDesiredDate'] is not True \
                    and snapshot.LifeCycle['isOlderThanDesiredDate'] is not True:
                inventory.append(snapshot)
        return inventory

    def get_rule(self, name, default=None):
        return self.rules[name] if name in self.rules else default

    def group_allowed(self, group):
        name = self.get_rule('name')
        regex = re.compile(name, re.IGNORECASE)
        if regex.findall(group):
            return True
        return False

    def get_timestamp(self, thing):
        if type(thing) in (datetime, datetime.date, datetime.time):
            return thing.timestamp()
        else:
            date_time = parser.parse(thing)
            return date_time.timestamp()


class GroupedSnapshots(DataCollection):

    def __init__(self, snapshots):
        data = {}
        for id, snapshot in snapshots.items():
            if snapshot.NameTag:
                if snapshot.NameTag not in data:
                    data[snapshot.NameTag] = []
                data[snapshot.NameTag].append(snapshot)

        DataCollection.__init__(self, data)


class VolumeCollection(DataCollection):

    def __init__(self, context, region=''):
        data = {}
        resources = context.get_from_aws_api(
            api_namespace='ec2', api_name='describe_volumes', api_response_key='Volumes', api_cache_ttl=context.cache_ttl,
            api_request_config={'PaginationConfig': {'MaxResults': 99999}}, region=region
        )
        for item in resources:
            data[item['VolumeId']] = Volume(**item)
        DataCollection.__init__(self, data)


class ImageCollection(DataCollection):

    def __init__(self, context, region=''):
        data = {}
        resources = context.get_from_aws_api(
            api_namespace='ec2', api_name='describe_images', api_response_key='Images', api_cache_ttl=context.cache_ttl,
            region=region,
            api_request_config={'Owners': ['self'], 'Filters': [{'Name': 'state', 'Values': ['available']}]}
        )
        for item in resources:
            data[item['ImageId']] = Image(**item)
        DataCollection.__init__(self, data)


class InstanceCollection(DataCollection):

    def __init__(self, context, region=''):
        data = {}
        resources = context.get_from_aws_api(
            api_namespace='ec2', api_name='describe_instances', api_response_key='Reservations',
            api_cache_ttl=context.cache_ttl,
            api_request_config={'PaginationConfig': {'MaxResults': 99999}}, region=region
        )
        for reservation in resources:
            for item in reservation['Instances']:
                data[item['InstanceId']] = Instance(**item)

        DataCollection.__init__(self, data)


class SnapshotCollection(DataCollection):
    ignore_description: list = [
        'Copied for DestinationAmi', 'ec2ab',
        'Created by AWS-VMImport', 'Created for policy', '[Copied snap-'
    ]

    def __init__(self, context, region=''):
        data = {}
        resources = context.get_from_aws_api(
            api_namespace='ec2', api_name='describe_snapshots', api_response_key='Snapshots', api_cache_ttl=context.cache_ttl,
            region=region,
            api_request_config={'OwnerIds': ['self'], 'PaginationConfig': {'MaxResults': 99999},
                                'Filters': [{'Name': 'status', 'Values': ['completed']}]}
        )
        for item in resources:
            can_add = True
            for ignored_prefix in self.ignore_description:
                if item['Description'].startswith(ignored_prefix):
                    can_add = False
                    break
            if can_add:
                data[item['SnapshotId']] = Snapshot(**item)

        DataCollection.__init__(self, data)


class SnapshotData(object):

    def __str__(self):
        return 'Snapshot Data'

    def __init__(self, context, region: str = ''):
        self.context = context
        self.region = region
        self.volumes = VolumeCollection(context, region)
        self.images = ImageCollection(context, region)
        self.instances = InstanceCollection(context, region)
        self.snapshots = SnapshotCollection(context, region)
        self.enrich_snapshots()

    def enrich_snapshots(self):

        for id, snapshot in self.snapshots.items():

            if snapshot.VolumeId in self.volumes:
                snapshot.Volume = self.volumes[snapshot.VolumeId]

                for attachment in snapshot.Volume.Attachments:
                    if attachment['InstanceId'] in self.instances:
                        snapshot.Instance = self.instances[attachment['InstanceId']]

            for image_id in snapshot.ParentImageIds:
                if image_id in self.images:
                    snapshot.Image = self.images[image_id]
            snapshot.build_nametag()  # we do this to ensure relations can be used if needed.


@dataclass
class Instance:
    AmiLaunchIndex: str = ""
    ImageId: str = ""
    InstanceId: str = ""
    InstanceType: str = ""
    KernelId: str = ""
    KeyName: str = ""
    LaunchTime: str = ""
    Platform: str = ""
    PrivateDnsName: str = ""
    PrivateIpAddress: str = ""
    PublicDnsName: str = ""
    PublicIpAddress: str = ""
    RamdiskId: str = ""
    StateTransitionReason: str = ""
    SubnetId: str = ""
    VpcId: str = ""
    Architecture: str = ""
    ClientToken: str = ""
    EbsOptimized: str = ""
    EnaSupport: str = ""
    Hypervisor: str = ""
    InstanceLifecycle: str = ""
    OutpostArn: str = ""
    RootDeviceName: str = ""
    RootDeviceType: str = ""
    SourceDestCheck: str = ""
    SpotInstanceRequestId: str = ""
    SriovNetSupport: str = ""
    VirtualizationType: str = ""
    CapacityReservationId: str = ""
    BootMode: str = ""
    PlatformDetails: str = ""
    UsageOperation: str = ""
    UsageOperationUpdateTime: str = ""
    Ipv6Address: str = ""
    MaintenanceOptions: str = ""
    Monitoring: dict = field(default_factory=dict)
    Placement: dict = field(default_factory=dict)
    ProductCodes: list = field(default_factory=list)
    State: dict = field(default_factory=dict)
    BlockDeviceMappings: list = field(default_factory=list)
    IamInstanceProfile: dict = field(default_factory=dict)
    ElasticGpuAssociations: list = field(default_factory=list)
    ElasticInferenceAcceleratorAssociations: list = field(default_factory=list)
    NetworkInterfaces: list = field(default_factory=list)
    SecurityGroups: list = field(default_factory=list)
    StateReason: dict = field(default_factory=dict)
    Tags: list = field(default_factory=list)
    CpuOptions: dict = field(default_factory=dict)
    CapacityReservationSpecification: dict = field(default_factory=dict)
    HibernationOptions: dict = field(default_factory=dict)
    Licenses: list = field(default_factory=list)
    MetadataOptions: dict = field(default_factory=dict)
    EnclaveOptions: dict = field(default_factory=dict)
    PrivateDnsNameOptions: dict = field(default_factory=dict)


@dataclass
class Volume:
    Attachments: list
    AvailabilityZone: str
    CreateTime: str
    Encrypted: bool
    Size: int
    SnapshotId: str
    State: str
    VolumeId: str
    VolumeType: str
    MultiAttachEnabled: bool

    FastRestored: bool = None
    Iops: int = None
    KmsKeyId: str = ""
    OutpostArn: str = ""
    Throughput: int = None
    Tags: list = field(default_factory=list)


@dataclass
class Image:
    Architecture: str
    CreationDate: str
    ImageId: str
    ImageLocation: str
    ImageType: str
    Public: bool
    OwnerId: str
    PlatformDetails: str
    UsageOperation: str
    State: str
    Hypervisor: str
    RootDeviceName: str
    RootDeviceType: str
    VirtualizationType: str
    SriovNetSupport: str = ""
    Name: str = ""
    KernelId: str = ""
    Platform: str = ""
    RamdiskId: str = ""
    Description: str = ""
    ImageOwnerAlias: str = ""
    BootMode: str = ""
    DeprecationTime: str = ""
    EnaSupport: bool = None
    ProductCodes: list = field(default_factory=list)
    BlockDeviceMappings: list = field(default_factory=list)
    StateReason: dict = field(default_factory=dict)
    Tags: list = field(default_factory=list)


@dataclass
class Snapshot:
    Encrypted: bool
    OwnerId: str
    Progress: str
    SnapshotId: str
    StartTime: str
    State: str
    VolumeId: str
    VolumeSize: int
    StorageTier: str

    # Defaulted attributes.
    Description: str = ""
    DataEncryptionKeyId: str = ""
    KmsKeyId: str = ""
    OutpostArn: str = ""
    OwnerAlias: str = ""
    StateMessage: str = ""
    RestoreExpiryTime: str = ""
    Tags: list = field(default_factory=list)

    # Custom attributes.
    Volume: dict = field(default_factory=dict)
    Image: dict = field(default_factory=dict)
    Instance: dict = field(default_factory=dict)
    ParentImageIds: list = field(default_factory=list)
    ParentSnapshotIds: list = field(default_factory=list)
    ParentVolumeIds: list = field(default_factory=list)
    ParentInstanceIds: list = field(default_factory=list)
    LifeCycle: dict = field(default_factory=dict)

    NameTag: str = ""
    CanDelete: bool = False
    CanDeleteReason: str = ""
    ActionSuggested: str = ""
    ActionReason: str = ""

    def __post_init__(self):
        self.parse_data_from_description()
        self.LifeCycle = {
            'isOldest': False,
            'isNewest': False,
            'isEol': False,
            'isOlderThanDesiredDate': False,
            'isNewerThanDesiredDate': False,
            'actionSuggested': '',
            'actionReasons': []
        }

    def parse_data_from_description(self, matched_desc_patterns=['i-', 'ami-', 'vol-', 'snap-']):
        pattern = re.compile('(?i)\\b[a-z]+-[a-z0-9]+')

        # try to parse the description for information that is useful.
        name_values = []
        for match in pattern.findall(self.Description):
            for match_pattern in matched_desc_patterns:
                if match.startswith(match_pattern):
                    name_values.append(match)

        # fallback to a best attempt with a normalized description.
        if not name_values:
            name_values.append(
                re.sub('[\W_]+', ' ', self.Description, flags=re.UNICODE).replace(' ', '-').lower()[0:24])

        # parse and add back into our class for relationship mappings.
        for item in name_values:
            self.ParentInstanceIds.append(item) if item.startswith('i-') else None
            self.ParentImageIds.append(item) if item.startswith('ami-') else None
            self.ParentVolumeIds.append(item) if item.startswith('vol-') else None
            self.ParentSnapshotIds.append(item) if item.startswith('snap-') else None

    def build_nametag(self):
        tags = []
        name_tag = self.get_by_key_match(self.Tags, 'Key', 'Name', 'Value')
        state_tags = []
        if name_tag:
            tags.append(name_tag)

        if self.Volume and self.Volume.Tags:
            name_tag = self.get_by_key_match(self.Volume.Tags, 'Key', 'Name', 'Value')
            state_tags.append('volume found')
            if name_tag and name_tag not in tags:
                tags.append(name_tag)
        else:
            state_tags.append('volume not found')

        if self.Instance and self.Instance.Tags:
            name_tag = self.get_by_key_match(self.Instance.Tags, 'Key', 'Name', 'Value')
            state_tags.append('instance found')
            if name_tag and name_tag not in tags:
                tags.append(name_tag)
        else:
            state_tags.append('instance not found')

        tags.append('{}'.format(self.VolumeId))
        self.NameTag = '[{}]'.format(']::['.join(tags + state_tags))

    def get_by_key_match(self, items, key, value, return_key=None, default=None):
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
