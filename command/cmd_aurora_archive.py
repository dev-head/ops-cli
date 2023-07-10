import click
from cli import pass_context
import sys
import re
import hashlib
import dateutil.parser as parser
import datetime

class SnapshotCollection:
    context = None
    config  = {
        'max_records':      9999,
        'cache_ttl':        0,
        'type':             'manual',
        'context':          '',
        'archive_bucket':   ''
    }

    def __init__(self, config):
        self.config     = config
        self.context    = config['context']
        self.snapshots  = list()

    def __iter__(self):
        items =  self.context.get_from_aws_api(
            api_namespace       = 'rds',
            api_name            = 'describe_db_cluster_snapshots',
            api_response_key    = 'DBClusterSnapshots',
            api_cache_ttl       = self.get_from_config('cache_ttl', 0),
            api_request_config  = {
                'SnapshotType':     self.get_from_config('type', 'manual'),
                'PaginationConfig': {'MaxRecords': self.get_from_config('max_records', 9999)}
            }
        )
        for item in items:
            yield SnapshotModel(item, {
                'context':          self.context,
                'archive_bucket':   self.get_from_config('archive_bucket')
            })

    def get_from_config(self, key, default_value = None):
        return self.config[key] if key in self.config else default_value

class SnapshotModel(object):
    config  = {
        'archive_bucket': ''
    }

    def get_from_config(self, key, default_value = None):
        return self.config[key] if key in self.config else default_value

    def __str__(self):
        return str(self.__dict__)

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def __delitem__(self, key):
        del self.__dict__[key]

    def __contains__(self, key):
        return key in self.__dict__

    def __len__(self):
        return len(self.__dict__)

    def __repr__(self):
        return repr(self.__dict__)

    def __init__(self, snapshot, config):
        self.config         = config

        if snapshot is not None:
            self.__dict__.update(snapshot)
            self['id']              = self.get_id()
            self['prefix']          = re.sub(r'^arn:(.*)cluster-snapshot:', '', self['DBClusterIdentifier'])
            self['s3_base_path']    = '{}/{}'.format(self['prefix'], self['id'])
            self.is_archived        = self.is_in_s3()
            self.is_okay_delete     = self.can_delete()

    def get_id(self):
        """
        AWS has a character limit of 60 for the export id
        we will use the snapshot id where possible as it's the most user friendly
        and default to the md5() of that snapshot id if we have to.
        They also require a letter char to start, so now we need to prefix the hash.
        We use a prefix to infer how to decode.
        :return:
        """
        id = self['DBClusterSnapshotIdentifier']
        if len(id) > 60:
            id = 'md5-id-{}'.format(hashlib.md5(self['DBClusterSnapshotIdentifier'].encode('utf-8')).hexdigest())

        return id

    def can_archive(self):
        return True if self['Status'].lower() == 'available' else False

    def can_delete(self):
        try:
            created_at = parser.parse(self['SnapshotCreateTime'])
        except TypeError:
            created_at = self['SnapshotCreateTime']

        time_now    = datetime.datetime.now(datetime.timezone.utc)
        time_diff   = ((time_now - created_at).days)

        if time_diff > 60 and self.is_archived:
            return True

        return False

    def delete(self):
        result = False
        if self.can_delete():
            result = self.get_from_config('context').get_from_aws_api(
                api_namespace       = 'rds',
                api_name            = 'delete_db_cluster_snapshot',
                api_response_key    = '',
                api_cache_ttl       = 0,
                api_request_config  = {
                    'DBClusterSnapshotIdentifier': self['DBClusterSnapshotIdentifier']
                }
            )
            # saving result as a log for debugging and historical retention.
            if result:
                self.get_from_config('context').put_cache('log.rds.delete_db_cluster_snapshot', result, 'a')

        return True if result else False

    def is_in_s3(self):
        search_key  = '{}/export_info_{}.json'.format(self['s3_base_path'], self['id'])
        result      =  self.get_from_config('context').get_from_aws_api(
            api_namespace       = 's3',
            api_response_key    = '',
            api_name            = 'head_object',
            api_cache_ttl       = 0,
            api_request_config  = {
                'Bucket':   self.get_from_config('archive_bucket'),
                'Key':      search_key,
            }
        )
        self['s3_key']  = search_key

        return True if result else False

class ExportQueueResponse(object):
    export_queue    = None

    def __init__(self, export_queue):
        if export_queue:
            self.export_queue   = export_queue

    def get_report(self, type = 'basic'):
        report_data = []
        if type == 'basic':
            report_data = [{
                'active_exports':       self.export_queue.get_state_count('active'),
                'added_to_queue':       self.export_queue.get_state_count('queued'),
                'queue_limit':          self.export_queue.batch_limit,
                'un_processed':         self.export_queue.get_state_count('un_processed'),
                'not_allowed':          self.export_queue.get_state_count('not_allowed'),
                'historical_completed': self.export_queue.get_state_count('completed')
            }]

        return report_data

class ExportQueue(object):
    context         = None
    response        = None
    raw_state       = []
    batch_limit     = 5 # AWS sets limit to five jobs.
    config          = {
        's3_bucket_name':   '',
        'iam_role_arn':     '',
        'kms_key_id':       '',
        'delete_snapshots': False
    }
    state           = {
        'active': {
            'allowed_status': ['started', 'in_progress', 'running', 'pending', 'starting'],
            'items': []
        },
        'completed': {
            'allowed_status': ['complete'],
            'items': []
        },
        'queued': {
            'allowed_status': ['internal'],
            'items': []
        },
        'un_processed': {
            'allowed_status': ['internal'],
            'items': []
        },
        'not_allowed': {
            'allowed_status': ['internal'],
            'items': []
        }
    }

    def __init__(self, config):
        # @todo: validate required configuration.
        self.config         = config
        self.context        = config['context']
        self.raw_state      = self.get_active_export_tasks()
        self.build_state()

    def get_response(self):
        return self.response

    def get_active_export_tasks(self):
        return self.context.get_from_aws_api(
            api_namespace       = 'rds',
            api_name            = 'describe_export_tasks',
            api_response_key    = 'ExportTasks',
            api_cache_ttl       = 0,
            api_request_config  = {
                'PaginationConfig': {'MaxRecords': 999}
            }
        )

    def get_snapshots(self):
        return self.context.get_from_aws_api(
            api_namespace       = 'rds',
            api_name            = 'describe_db_cluster_snapshots',
            api_response_key    = 'DBClusterSnapshots',
            api_cache_ttl       = 3600,
            api_request_config  = {
                'SnapshotType': 'manual',
                'PaginationConfig': {'MaxRecords': 999}
            }
        )

    def is_snapshot_valid(self, snapshot):
        """
        @todo: consider other steps to validate, age of snapshot for one.
        :param snapshot:
        :return: Bool
        """

        skip_unsupported_engine_modes = ["serverless"]
        if snapshot['EngineMode'] in skip_unsupported_engine_modes:
            return False

        if self.is_snapshot_exporting(snapshot):
            return False

        if self.is_snapshot_in_s3(snapshot):
            return False

        return True

    def get_from_config(self, key, default_value = None):
        return self.config[key] if key in self.config else default_value

    def fill_open_queue(self):
        snapshots = self.get_snapshots()

        for item in snapshots:
            if self.is_open():

                snapshot    =  SnapshotModel(item, {
                    'context': self.context,
                    'archive_bucket': self.get_from_config('s3_bucket_name')
                })

                if self.is_snapshot_valid(snapshot):
                    self.add_item_to_state('queued', snapshot)
                else:
                    self.add_item_to_state('not_allowed', snapshot)
                    self.context.dlog('[fill_open_queue]::[snap-not-allowed-to-archive]::[{}]'.format(snapshot['id']))
            else:
                self.add_item_to_state('un_processed', item)
                queue_used = self.get_state_count('queued') + self.get_state_count('active')
                self.context.dlog('[ExportQueue]::[run]::[queue closed]::[slots used]::[{} of {}]'.format(queue_used, self.batch_limit))

    def process_queued(self):
        queued_items    = self.state['queued']['items']
        for item in queued_items:
            try:
                self.process_queued_item(item)
            except Exception as e:
                self.context.vlog('[process_queued_item]::[failed]::[{}]::[{}]').format(e, item)

    def process_queued_item(self, item):
        self.context.dlog('[ExportQueue]::[process_queued_item]::[{}]'.format(item['s3_base_path']))

        if self.config['dry_run'] is True:
            print('')
            print('#-{Dry Run Queued Item}----------------------#')
            print({
                'ExportTaskIdentifier': item['id'],
                'SourceArn':            item['DBClusterSnapshotArn'],
                'S3BucketName':         self.config['s3_bucket_name'],
                'IamRoleArn':           self.config['iam_role_arn'],
                'KmsKeyId':             self.config['kms_key_id'],
                'S3Prefix':             item['prefix']
            })
            print('#--------------------------------------------#')
            print('')
        else:
            result  =  self.context.get_from_aws_api(
                api_namespace       = 'rds',
                api_name            = 'start_export_task',
                api_response_key    = '',
                api_cache_ttl       = 0,
                api_request_config  = {
                    'ExportTaskIdentifier': item['id'],
                    'SourceArn':            item['DBClusterSnapshotArn'],
                    'S3BucketName':         self.config['s3_bucket_name'],
                    'IamRoleArn':           self.config['iam_role_arn'],
                    'KmsKeyId':             self.config['kms_key_id'],
                    'S3Prefix':             item['prefix']
                }
            )

            if 'FailureCause' in result:
                self.context.vlog('[FAILURE]::[{}]').format(result['FailureCause'])

            if 'WarningMessage' in result:
                self.context.vlog('[WARN]::[{}]').format(result['WarningMessage'])

    def can_delete_snapshots(self):
        return self.config['delete_snapshots']

    def test(self):

        # we want to test the kms key early in case there's permission issues.
        if self.config['kms_key_id']:
            try:
                kms_key = self.context.get_from_aws_api(
                    api_namespace='kms',
                    api_name='describe_key',
                    api_response_key='KeyMetadata',
                    api_cache_ttl=0,
                    api_request_config={'KeyId': self.config['kms_key_id']}
                )
            except Exception as e:
                raise Exception('Failed KMS Access test, please check permission on [{}]::[error]::{}'.format(self.config['kms_key_id'], e))

    def run(self):
        self.test()
        self.fill_open_queue()
        self.process_queued()
        self.response   = ExportQueueResponse(self)

    def get_s3_prefixes(self):
        return self.context.get_from_aws_api(
            api_namespace       = 's3',
            api_name            = 'list_objects_v2',
            api_response_key    = 'CommonPrefixes',
            api_cache_ttl       = 60,
            api_request_config  = {
                'PaginationConfig': {'MaxRecords': 20},
                'Bucket':           self.config['s3_bucket_name'],
                'Delimiter':        '/',
                'MaxKeys':          10
            }
        )

    def is_snapshot_in_s3(self, snapshot):
        search_key  = '{}/export_info_{}.json'.format(snapshot['s3_base_path'], snapshot['id'])
        self.context.dlog('[is_snapshot_in_s3]::[search_key]::[{}]'.format(search_key))

        result =  self.context.get_from_aws_api(
            api_namespace       = 's3',
            api_response_key    = '',
            api_name            = 'head_object',
            api_cache_ttl       = 0,
            api_request_config  = {
                'Bucket':   self.config['s3_bucket_name'],
                'Key':      search_key,
            }
        )
        self.context.dlog(result)
        return True if result else False

    def is_open(self):
        queue_used  = self.get_state_count('queued') + self.get_state_count('active')
        self.context.dlog('[queue]::[is_open]::[{} of {}]'.format(queue_used, self.batch_limit))
        return True if queue_used < self.batch_limit else False

    def get_state_count(self, type):
        return len(self.state[type]['items'])

    def is_snapshot_exporting(self, snapshot):
        for item in self.state['active']['items']:
            if snapshot['id'] == item['ExportTaskIdentifier']:
                return True
        return False

    def get_snapshot_state(self, snapshot):
        for item in self.raw_state:
            if snapshot['id'] in item['ExportTaskIdentifier']:
                return item

    def add_item_to_state(self, type, item):
        if type in self.state:
            self.state[type]['items'].append(item)

    def build_state(self):
        for item in self.raw_state:
            status_name     = item['Status'].lower()
            for state_name, state in self.state.items():
                if status_name in state['allowed_status']:
                    self.add_item_to_state(state_name, item)

def get_active_export_tasks(ctx):

    return ctx.get_from_aws_api(
        api_namespace       = 'rds',
        api_name            = 'describe_export_tasks',
        api_response_key    = 'ExportTasks',
        api_cache_ttl       = 0,
        api_request_config  = {
            'PaginationConfig': {'MaxRecords': 20}
        }
    )

def get_snapshots(ctx):
    return ctx.get_from_aws_api(
        api_namespace       = 'rds',
        api_name            = 'describe_db_cluster_snapshots',
        api_response_key    = 'DBClusterSnapshots',
        api_cache_ttl       = 3600,
        api_request_config  = {
            'SnapshotType':     'manual',
            'PaginationConfig': {'MaxRecords': 20}
        }
    )

def output_as_csv(headers, output):
    import csv
    writer = csv.DictWriter(sys.stdout, fieldnames=headers)
    writer.writeheader()
    for item in output:
        writer.writerow({k: v for k, v in item.items() if k in headers})

#-{CLI Commands}-------------------------------------------------------------------------------------------------------#

@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@pass_context
def subcmd(ctx, profile, verbose, debug):
    """does stuff for you."""
    ctx.obj['aws_profile']  = profile
    ctx.verbose             = verbose
    ctx.debug               = debug

@subcmd.command()
@pass_context
def describe_manual_snapshots(ctx):
    ctx.vlog('[describe_manual_snapshots]::[started]'.format())
    print(get_snapshots(ctx))
    ctx.vlog('[describe_manual_snapshots]::[completed]'.format())

@subcmd.command()
@pass_context
def describe_active_exports(ctx):
    ctx.vlog('[describe_active_exports]::[started]'.format())
    res = get_active_export_tasks(ctx)
    output_as_csv(['SourceArn', 'ExportTaskIdentifier', 'Status', 'PercentProgress', 'S3Bucket', 'S3Prefix', 'TotalExtractedDataInGB'], res)
    ctx.vlog('[describe_active_exports]::[completed]'.format())

@subcmd.command()
@click.option('--s3-bucket-name', envvar="S3_BUCKET_NAME", default="", help='S3 Bucket name to sync snapshots to.')
@click.option('--iam-role-arn', envvar="IAM_ROLE_ARN", default="", help='IAM Role ARN used by the export service.')
@click.option('--kms-key-id', envvar="KMS_KEY_ID", default="", help='KMS Key Id used to encrypt the export.')
@click.option('--dry-run', envvar='DRY_RUN', is_flag=True, default=False, help='Enables a Dry run (no export)')
@pass_context
def export_to_s3(ctx, s3_bucket_name, iam_role_arn, kms_key_id, dry_run):
    ctx.vlog('[export_to_s3]::[started]'.format())
    ctx.dlog('[export_to_s3]::[s3_bucket_name]::[{}]'.format(s3_bucket_name))
    ctx.dlog('[export_to_s3]::[iam_role_arn]::[{}]'.format(iam_role_arn))
    ctx.dlog('[export_to_s3]::[kms_key_id]::[{}]'.format(kms_key_id))
    ctx.dlog('[export_to_s3]::[dry_run]::[{}]'.format(dry_run))

    queue   = ExportQueue({
        'context':          ctx,
        's3_bucket_name':   s3_bucket_name,
        'iam_role_arn':     iam_role_arn,
        'kms_key_id':       kms_key_id,
        'dry_run':          dry_run
    })

    queue.run()
    report = queue.get_response().get_report('basic')
    output_as_csv(report[0].keys(), report)
    ctx.vlog('[export_to_s3]::[completed]'.format())

@subcmd.command()
@click.option('--s3-bucket-name', envvar="S3_BUCKET_NAME", default="", help='S3 Bucket name to sync snapshots to.')
@click.option('--iam-role-arn', envvar="IAM_ROLE_ARN", default="", help='IAM Role ARN used by the export service.')
@click.option('--kms-key-id', envvar="KMS_KEY_ID", default="", help='KMS Key Id used to encrypt the export.')
@click.option('--dry-run', envvar='DRY_RUN', is_flag=True, default=False, help='Enables a Dry run (no export)')
@click.option('--limit', envvar='LIMIT', default=1, help='Limit number of snapshots deleted; zero to have no limit.')
@pass_context
def delete_snapshots(ctx, s3_bucket_name, iam_role_arn, kms_key_id, dry_run, limit):
    """
    Delete's snapshots that have been saved already and meet our logical controls.
    * For each snapshot
        * Has the snapshot been archived?
        * Is the snapshot greater than (60) days?

    :param ctx:
    :return:
    """
    ctx.vlog('[delete_snapshots]::[started]'.format())
    ctx.dlog('[delete_snapshots]::[s3_bucket_name]::[{}]'.format(s3_bucket_name))
    ctx.dlog('[delete_snapshots]::[iam_role_arn]::[{}]'.format(iam_role_arn))
    ctx.dlog('[delete_snapshots]::[kms_key_id]::[{}]'.format(kms_key_id))
    ctx.dlog('[delete_snapshots]::[dry_run]::[{}]'.format(dry_run))
    ctx.dlog('[delete_snapshots]::[limit]::[{}]'.format(limit))

    snapshots   = SnapshotCollection({
        'max_records'   : 9999,
        'cache_ttl'     : 0,
        'type'          : 'manual',
        'context'       : ctx,
        'archive_bucket':  s3_bucket_name
    })

    print('Name, Is Archived, Is Deletable, Deleted, Snapshot Created, S3 Bucket, S3 Path')

    count = 0
    for snapshot in snapshots:

        if count < limit or limit == 0:
            if not dry_run:
                is_deleted  = snapshot.delete()
            else:
                is_deleted  = "Dry Run"

            print('{},{},{},{},{},{},{}'.format(
                snapshot['id'], snapshot.is_archived, snapshot.is_okay_delete,
                is_deleted, snapshot['SnapshotCreateTime'], s3_bucket_name, snapshot['s3_key']
            ))

            if is_deleted == True or is_deleted == 'Dry Run':
                count += 1
        else:
            break

    ctx.vlog('[delete_snapshots]::[completed]'.format())
