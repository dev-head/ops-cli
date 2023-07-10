Ops CLI
=======

State 
-----
This project is in an explorative state; built on subset of use cases that I have leveraged in the past. Having an easy way to buld CLI's in python is what drove this to creation. It's based on a previous version that I had created in PHP which had a few other commands. I chose python for this project due to it better aligning with experience we more commonly see in an operations team.

Description
-----------
This project is leveraged to provide a framework to execute commands via a common CLI; with an initial focus on using AWS API to help support common tasks that require unique functionality not otherwise provided by IOC or the AWS Console. 

Ways to Use
-----------
This cli is designed to be encapculated in docker and executed locally; additional support to be executed as a Lambda function for automation needs.

Commands
--------
> NOTE: Each command available has a detailed set of documents, linked below for reference.
- [run_plan](./documentation/commands/run_plan.md) Execute one or more bash commands, over ssh, on one or more target EC2 nodes.
- [ec2_encrypt](./documentation/commands/ec2_encrypt.md) Migrate one or more EC2 EBS volumes to be encrypted.
- [tag_resources](./documentation/commands/tag_resources.md) Normalize or update tagging across all supported resources.
- [aurora_archive](./documentation/commands/aurora_archive.md) Aurora RDS Snapshot life cycle commands.
- [ec2-archives](./documentation/commands/ec2-archives.md) EC2 Snapshot Cleaning. 
- [iam](./documentation/commands/iam.md) IAM Reporting.


Project Documentation 
---------------------
> The functionality contained in this application is further documented here. 
* [Development](./documentation/DEVELOPMENT.md)
* [Terraform](./terraform/README.md)

Versions
--------
- `python:3.7` (Core language)
- `click==7.1.2` (Underlying Python CLI Framework)
- `paramiko==2.8.1` (SSH Connections)