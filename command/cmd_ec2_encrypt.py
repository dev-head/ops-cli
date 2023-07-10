import click
import boto3
from cli import pass_context
import botocore
import sys

#
# @source https://github.com/dwbelliston/aws_volume_encryption
#
@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name.')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@pass_context
def subcmd(ctx, profile, verbose, debug):
    """does stuff for you."""
    ctx.obj['aws_profile'] = profile
    ctx.verbose = verbose
    ctx.debug   = debug


@subcmd.command()
@click.option('--instance-id', help='Instance Id to migrate', multiple=True)
@click.option('--kms-key', default="", help='Optional KMS Key To use.')
@click.option('--cleanup-please', is_flag=True, default=False, help='If passed, the old snapshot,encrypted snapshot and old volume are deleted.')
@pass_context
def encrypt_instances(ctx, instance_id, kms_key, cleanup_please):
    log_prefix      = '[migrate_instance]'.format()
    ctx.instance_id = instance_id
    ctx.kms_key     = kms_key
    ctx.vlog('{}::[started]'.format(log_prefix))
    ctx.vlog('{}::[instance_id]::[{}]'.format(log_prefix, instance_id))
    ctx.vlog('{}::[kms_key]::[{}]'.format(log_prefix, str(kms_key)))
    ctx.vlog('{}::[aws_profile]::[{}]'.format(log_prefix, str(ctx.obj['aws_profile'])))

    client  = get_aws_client(ctx, 'ec2')
    waiter_instance_exists = client.get_waiter('instance_exists')

    for id in instance_id:

        ctx.vlog('{}::[get_instance]::[{}]'.format(log_prefix, str(id)))
        try:
            instance = get_instance(ctx, id)
            waiter_instance_exists.wait(InstanceIds=[id])
        except Exception as e:
            sys.exit('ERROR: {}'.format(e))

        if instance:
            ctx.vlog('{}::[instance_exists]::[{}]'.format(log_prefix, str(id)))
            shutdown_instance(ctx, instance)
            volume_data = encrypt_instance_volumes(ctx, instance)
            start_instance(ctx, instance)

            for cleanup in volume_data:
                if cleanup_please:
                    ctx.log('{}::[removing snapshot]::[{}]'.format(log_prefix, cleanup['snapshot'].id))
                    cleanup['snapshot'].delete()

                    ctx.log('{}::[removing encrypted snapshot]::[{}]'.format(log_prefix, cleanup['snapshot_encrypted'].id))
                    cleanup['snapshot_encrypted'].delete()

                    ctx.log('{}::[removing original volume]::[{}]'.format(log_prefix, cleanup['volume'].id))
                    cleanup['volume'].delete()
                else:
                    ctx.log('{}::[please remove snapshot]::[{}]'.format(log_prefix, cleanup['snapshot'].id))
                    ctx.log('{}::[please remove encrypted snapshot]::[{}]'.format(log_prefix, cleanup['snapshot_encrypted'].id))
                    ctx.log('{}::[please remove original volume::[{}]]'.format(log_prefix, cleanup['volume'].id))

            ctx.vlog('{}::[completed encryption migration]::[{}]'.format(log_prefix, instance.id))

    ctx.vlog('{}::[completed]'.format(log_prefix))


def get_aws_client(ctx, client_name = "ec2"):
    if 'client_' + client_name in ctx.obj:
        ctx.dlog('[get_aws_client]::[using existing session]')
        client = ctx.obj['client_' + client_name]
    else:
        ctx.dlog('[get_aws_client]::[staring]::[get_aws_session ]')
        session     = get_aws_session(ctx)
        client      = session.client(client_name)
        ctx.obj['client_' + client_name]    = client

    return client


def get_aws_session(ctx):
    if 'session' in ctx.obj and ctx.obj['session'] is not None:
        ctx.dlog('[get_aws_session]::[using existing session]')
        session = ctx.obj['session']
    elif ctx.obj['aws_profile'] != "":
        ctx.dlog('[get_aws_session]::[starting session]::[with profile]::[{}]'.format(ctx.obj['aws_profile']))
        session = boto3.session.Session(profile_name=ctx.obj['aws_profile'])
    else:
        ctx.dlog('[get_aws_session]::[starting session]::[no profile]')
        session = boto3.session.Session()

    ctx.obj['region']   = session.region_name
    ctx.obj['session']  = session
    ctx.dlog('[get_aws_session]::[region]::[{}]'.format(ctx.obj['region']))

    return session


def get_instance(ctx, instance_id):
    session                 = get_aws_session(ctx)
    client                  = get_aws_client(ctx, 'ec2')
    ec2                     = session.resource('ec2')
    instance                = ec2.Instance(instance_id)
    waiter_instance_exists  = client.get_waiter('instance_exists')

    try:
        ctx.vlog('[get_instance]::[waiter_instance_exists]::[{}]'.format(instance_id))
        waiter_instance_exists.wait(InstanceIds=[instance_id])
    except botocore.exceptions.WaiterError as e:
        sys.exit('[ERROR]::[get_instance]::[{}]'.format(e))

    if is_available(instance) is not True:
        sys.exit('ERROR: Instance is {} please make sure this instance is active.'.format(instance.state['Name']))

    return instance


def is_available(instance):
    instance_exit_states = [0, 32, 48]
    if instance.state['Code'] in instance_exit_states:
        return False
    return True


def shutdown_instance(ctx, instance):
    client                                      = get_aws_client(ctx, 'ec2')
    waiter_instance_stopped                     = client.get_waiter('instance_stopped')
    waiter_instance_stopped.config.max_attempts = 80

    if instance.state['Code'] is 16:
        instance.stop()

    try:
        ctx.vlog('[shutdown_instance]::[waiter_instance_stopped]::[{}]'.format(instance.id))
        waiter_instance_stopped.wait(InstanceIds=[instance.id])
    except botocore.exceptions.WaiterError as e:
        sys.exit('ERROR: {}'.format(e))

    return True


def get_device_mappings(instance):
    all_mappings            = []
    block_device_mappings   = instance.block_device_mappings

    for device_mapping in block_device_mappings:
        original_mappings = {
            'DeleteOnTermination':  device_mapping['Ebs']['DeleteOnTermination'],
            'VolumeId':             device_mapping['Ebs']['VolumeId'],
            'DeviceName':           device_mapping['DeviceName']
        }
        all_mappings.append(original_mappings)

    return all_mappings


def get_volumes(instance):
    volumes = [v for v in instance.volumes.all()]
    for volume in volumes:
        if volume.encrypted:
            sys.exit('[get_volumes]::[{}]::[{}]::[is already encrypted]'.format(instance.id, volume.id))
    return volumes


def encrypt_instance_volumes(ctx, instance):
    volumes         = get_volumes(instance)
    all_mappings    = get_device_mappings(instance)
    volume_data     = []

    for volume in volumes:

        current_volume_data = {}
        for mapping in all_mappings:
            if mapping['VolumeId'] == volume.volume_id:
                current_volume_data = {
                    'volume': volume, 'DeleteOnTermination': mapping['DeleteOnTermination'], 'DeviceName': mapping['DeviceName'],
                }

        snapshot            = create_snapshot(ctx, instance, volume)
        snapshot_encrypted  = create_encrypted_snapshot(ctx, instance, volume, snapshot)
        volume_encrypted    = create_encrypted_volume(ctx, instance, volume, snapshot, snapshot_encrypted)
        detached            = detatch_current_volume(ctx, instance, volume, snapshot, snapshot_encrypted, volume_encrypted, current_volume_data)
        current_volume_data = attach_encrypted_volume(ctx, instance, volume, snapshot, snapshot_encrypted, volume_encrypted, current_volume_data)
        volume_data.append(current_volume_data)

    update_device_mappings(instance, volume_data)
    return volume_data


def create_snapshot(ctx, instance, volume):
    session                                         = get_aws_session(ctx)
    client                                          = get_aws_client(ctx, 'ec2')
    ec2                                             = session.resource('ec2')
    waiter_snapshot_complete                        = client.get_waiter('snapshot_completed')
    waiter_snapshot_complete.config.max_attempts    = 240
    desc                                            = '[ops-cli]::[pre-encrypted]::[{}]::[{}]'.format(instance.id, volume.id)
    snapshot                                        = ec2.create_snapshot(VolumeId=volume.id, Description=desc)

    try:
        ctx.vlog('[create_snapshot_real]::[waiter_snapshot_complete]::[{}]::[{}]'.format(instance.id, snapshot.id))
        waiter_snapshot_complete.wait(SnapshotIds=[snapshot.id])
    except botocore.exceptions.WaiterError as e:
        snapshot.delete()
        sys.exit('ERROR: {}'.format(e))

    return snapshot


def create_encrypted_snapshot(ctx, instance, volume, snapshot):
    region                      = ctx.obj['region']
    kms_key                     = ctx.kms_key
    session                     = get_aws_session(ctx)
    client                      = get_aws_client(ctx, 'ec2')
    ec2                         = session.resource('ec2')
    desc                        = '[ops-cli]::[encrypted]::[{}]::[{}]::[{}]'.format(instance.id, volume.id, snapshot.id)
    waiter_snapshot_complete    = client.get_waiter('snapshot_completed')

    if kms_key:
        snapshot_encrypted_dict = snapshot.copy(SourceRegion=region, Description=desc, KmsKeyId=kms_key, Encrypted=True)
    else:
        snapshot_encrypted_dict = snapshot.copy(SourceRegion=region, Description=desc, Encrypted=True)

    snapshot_encrypted = ec2.Snapshot(snapshot_encrypted_dict['SnapshotId'])
    try:
        ctx.vlog('[create_encrypted_snapshot]::[waiter_snapshot_complete]::[{}]::[{}]::[from: {}]::[to: {}]'
                 .format(instance.id, volume.id, snapshot.id, snapshot_encrypted.id))
        waiter_snapshot_complete.wait(SnapshotIds=[snapshot_encrypted.id])
    except botocore.exceptions.WaiterError as e:
        snapshot.delete()
        snapshot_encrypted.delete()
        sys.exit('ERROR: {}'.format(e))

    return snapshot_encrypted


def create_encrypted_volume(ctx, instance, volume, snapshot, snapshot_encrypted):
    session                 = get_aws_session(ctx)
    client                  = get_aws_client(ctx, 'ec2')
    ec2                     = session.resource('ec2')
    waiter_volume_available = client.get_waiter('volume_available')

    if volume.volume_type == 'io1':
        volume_encrypted = ec2.create_volume(
            SnapshotId=snapshot_encrypted.id,
            VolumeType=volume.volume_type,
            Iops=volume.iops,
            AvailabilityZone=instance.placement['AvailabilityZone']
        )
    else:
        volume_encrypted = ec2.create_volume(
            SnapshotId=snapshot_encrypted.id,
            VolumeType=volume.volume_type,
            AvailabilityZone=instance.placement['AvailabilityZone']
        )

    try:
        ctx.vlog('[create_encrypted_volume]::[waiter_volume_available]::[{}]::[from: {}]::[to: {}]'
                 .format(instance.id, snapshot_encrypted.id, volume_encrypted.id))
        waiter_volume_available.wait(VolumeIds=[volume_encrypted.id])
    except botocore.exceptions.WaiterError as e:
        snapshot.delete()
        snapshot_encrypted.delete()
        volume_encrypted.delete()
        sys.exit('ERROR: {}'.format(e))

    if volume.tags:
        volume_encrypted.create_tags(Tags=volume.tags)

    return volume_encrypted


def detatch_current_volume(ctx, instance, volume, snapshot, snapshot_encrypted, volume_encrypted, current_volume_data):
    client  = get_aws_client(ctx, 'ec2')
    waiter_volume_available = client.get_waiter('volume_available')

    instance.detach_volume(VolumeId=volume.id, Device=current_volume_data['DeviceName'])
    try:
        ctx.vlog('[create_encrypted_volume]::[waiter_volume_available]::[{}]::[detatching: {}]'.format(instance.id, volume.id))
        waiter_volume_available.wait(VolumeIds=[volume.id])
    except botocore.exceptions.WaiterError as e:
        snapshot.delete()
        snapshot_encrypted.delete()
        volume_encrypted.delete()
        sys.exit('ERROR: {}'.format(e))

    return None


def attach_encrypted_volume(ctx, instance, volume, snapshot, snapshot_encrypted, volume_encrypted, current_volume_data):
    client                  = get_aws_client(ctx, 'ec2')
    waiter_volume_in_use    = client.get_waiter('volume_in_use')
    instance.attach_volume(VolumeId=volume_encrypted.id, Device=current_volume_data['DeviceName'])

    try:
        ctx.vlog('[attach_encrypted_volume]::[waiter_volume_in_use]::[{}]::[attatching: {}]'.format(instance.id, volume_encrypted.id))
        waiter_volume_in_use.wait(VolumeIds=[volume_encrypted.id])
    except botocore.exceptions.WaiterError as e:
        snapshot.delete()
        snapshot_encrypted.delete()
        volume_encrypted.delete()
        sys.exit('ERROR: {}'.format(e))

    current_volume_data['snapshot']             = snapshot
    current_volume_data['snapshot_encrypted']   = snapshot_encrypted
    return current_volume_data


def update_device_mappings(instance, volume_data):
    for bdm in volume_data:
        instance.modify_attribute(
            BlockDeviceMappings=[
                {'DeviceName': bdm['DeviceName'], 'Ebs': {'DeleteOnTermination': bdm['DeleteOnTermination']}},
            ],
        )
    return None


def start_instance(ctx, instance):
    client  = get_aws_client(ctx, 'ec2')
    instance.start()
    waiter_instance_running = client.get_waiter('instance_running')

    try:
        ctx.vlog('[start_instance]::[waiter_instance_running]::[{}]'.format(instance.id))
        waiter_instance_running.wait(InstanceIds=[instance.id])
    except botocore.exceptions.WaiterError as e:
        sys.exit('ERROR: {}'.format(e))