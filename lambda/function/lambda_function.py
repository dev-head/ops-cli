"""
This is the entry point for lambda interface to call the cli.


"""
import logging
import json
import boto3
import subprocess

logger = logging.getLogger()
logger.setLevel(logging.ERROR)

def get_command(path, config):
    logger.debug('[{}]::[begin]'.format('get_command_as_args'))
    command_args = []

    if path:
        command_args.append(path)

    if config['command']:
        command_args.append(config['command'])

    if config['command_arguments']:
        for arg in config['command_arguments']:
            command_args.append(arg)

    if config['command_options']:
        for k, v in config['command_options'].items():
            command_args.append('{} "{}"'.format(k, v))

    if config['function']:
        command_args.append(config['function'])

    if config['function_arguments']:
        for arg in config['function_arguments']:
            command_args.append(arg)

    if config['function_options']:
        for k, v in config['function_options'].items():
            command_args.append('{} "{}"'.format(k, v))

    logger.debug('[{}]::[finished]'.format('get_command_as_args'))

    return command_args

def run_command(path, config):
    try:
        logger.debug('[{}]::[begin]::[{}]'.format('run_command', config))
        command_list    = get_command(path, config)
        command_str     = ' '.join(command_list)
        logger.info('[{}]::[command]::[{}]'.format('run_command', command_str))
        p = subprocess.run(command_str, stdout=subprocess.PIPE, shell=True)
        logger.debug('[{}]::[completed]::[{}]'.format('run_command', p.stdout))
        print(p.stdout.decode('UTF-8'))
    except Exception as e:
        logger.error("Ohh nice Exception: {}".format(e))
        return False

    return True

def lambda_handler(event, context):
    """

    :param event: example event format
    {
      "command": "example",
      "function": "hello",
      "command_options": {},
      "command_arguments": [],
      "function_arguments": [
        "Zorth McFaceTest"
      ],
      "function_options": {}
    }
    :param context:
    :return:
    """
    return run_command('/opt/ops-cli.deploy/bin/cli.lambda.py', event)
