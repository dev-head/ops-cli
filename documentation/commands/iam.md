Command :: IAM
===============

Description 
-----------
The initial use of this command is to pull a csv report from IAM roles.


### Command ListRoles [`list-role`]
- `--limit` Optionally used to define a limit. 

#### Usage 
```commandline
docker-compose run --rm tools iam  --profile NamedProfileHere list-roles --limit 1
```

#### Example CSV Output 
```
[CSV OUTPUT]===============================================================================================
Name,Description,DateCreated,DateLastUsed,RegionLastUsed
AccessAnalyzerBlahBlah,ExampleRole,2021-06-09 00:10:15+00:00,2021-06-09 00:14:00+00:00,us-east-1
===========================================================================================================
```