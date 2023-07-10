import click
from cli import pass_context

@click.group()
@click.option('--profile', envvar='PROFILE', default="", help='AWS Configuration Profile Name')
@click.option('-v', '--verbose', envvar='VERBOSE', is_flag=True, default=False, help='Enables verbose mode.')
@click.option('-d', '--debug', envvar='DEBUG', is_flag=True, default=False, help='Enables verbose debug mode.')
@pass_context
def subcmd(ctx, profile, verbose, debug):
    """does stuff for you."""
    ctx.obj['aws_profile'] = profile
    ctx.verbose = verbose
    ctx.debug   = debug

@subcmd.command()
@click.argument('names', nargs=-1)
@pass_context
def hello(ctx, names):
    log_prefix = '[hello]'
    for name in names:
        ctx.log('{}::[{}]'.format(log_prefix, str(name)))



@subcmd.command()
@click.argument('names', nargs=-1)
@pass_context
def goodbye(ctx, names):
    log_prefix = '[goodbye]'
    for name in names:
        ctx.log('{}::[{}]'.format(log_prefix, str(name)))