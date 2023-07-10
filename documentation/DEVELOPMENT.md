Development 
===========

Workflow
--------
* clone repo
* Configure environment vars (if needed): `cp env.dist local.env`
* Install Dependencies: `docker-compose run --rm install_vendors`
* Run example: `docker-compose run --rm tools example hello world`
* Place new commands in this format `command/cmd_${command_name}.py` "${command_name}" should be replaced with the name of your command.
* Use `command/cmd_example.py` as a basic example to start from.
* If you run into a weird build error, try removing your vendors/* and running dep install command cleanly.

  
Dependencies 
------------
- Click
    - [Click] provides a framework for base CLI features and code faster.
- Boto3
    - [Boto3] provides python library to make AWS API calls.
- Fabric
    - [Fabric] provides python library to support SSH connections.
- paramiko
  - [Paramiko]   provides python ssh library that fabric uses.
  - version pinned to `2.8.1` due to some changes that broke previous working functionality.
    - Related [Git Issue](https://github.com/paramiko/paramiko/issues/1612)
- PyYAML
    - [PyYAML] provides yaml parsing for local configuration files.

Development Dependencies 
------------------------
- Docker 
- Docker compose 
- Git 


References 
----------
- [Click](http://click.pocoo.org/5/)
- [Boto3](http://boto3.readthedocs.io/)
- [Fabric](http://www.fabfile.org/)
