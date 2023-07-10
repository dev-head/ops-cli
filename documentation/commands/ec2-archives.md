Command :: EC2 Archive
======================

Description 
-----------
The purpose of this command is to delete old snapshots; when you are dealing with an extraordinary amount, this script 
is very helpful in that you can target based on name, remove by specific date, retain by specific date, retain oldest, 
and retain newest as well as retain anything that is considered a "final" (EOL) snapshot.

How it works
------------
Based on the options set by you or by default, the script works to create groups of snapshots with each group running
the rules against it to determine what should be retained/removed. These groups are created dynamically based off of 
a compiled "NameTag"; this name is derived from the Name tag, name or id of any found sourced volume, name of any found sourced 
instance name/id. this allows us to capture snapshots that are specifically related and provide you the ability to 
weigh decisions to retain / remove based on that specific grouping. 

The `interactive` option, if passed, will output the decisions being calculated for each snapshot and then present you with an 
opportunity to approve the suggested targets or exit. This output will denote "remove" or "retain" for each snapshot, 
and list the reasons why that decision was made. This is an important step, as it gives you the user, the ability 
to see what is being suggested based on the rules defined; it is an opportunity to review and ensure your desired 
outcomes are going to run. Choosing no, will simply exit and no more action is completed; otherwise Yes will result 
in the snapshots that are targeted to as 'remove' action, to be removed. 

Considerations
--------------
- If an AMI exists for a given snapshot, it can not be deleted and you will see this message in the output.
- We use cache heavily due to the size of the dataset, if you re-run the same delete targets you'll see snapshots not found.
  - Please set the --cache-ttl option in the main command in order to override the default 9999999999 seconds.      

Command :: Default 
------------------
```shell
$> docker-compose run --rm tools ec2-archives --help
...
Usage: cli.py ec2-archives [OPTIONS] COMMAND [ARGS]...

  EC2 Archives command was created to help manage AWS EC2 Snapshots.

Options:
  --profile TEXT    AWS Configuration Profile Name
  -v, --verbose     Enables verbose mode.
  -d, --debug       Enables verbose debug mode.
  -y, --dry-run     Enables a Dry run (no changes)
  --cache-ttl TEXT  Optionally set local API cache result ttl (Default:
                    9999999999

  --help            Show this message and exit.

Commands:
  purge-snapshots
```

Command :: Purge E2 Snapshot (purge-snapshots) 
----------------------------------------------
```shell
$> docker-compose run --rm tools ec2-archives --profile NamedProfileHere purge-snapshots --help
...
Usage: cli.py ec2-archives purge-snapshots [OPTIONS]
  
  EC2 Archives :: purge_snapshots command was created to identify and purge
  AWS EC2 Snapshots. There are newer built in tools that support managing
  EC2 Snapshots, those should be considered before using this. This command
  is designed to safely attempt to categorize and retain based on user
  supplied filters; this is most useful when amd if the need arises to clear
  out unmanaged EC2 Snapshots, or at least view them with some stronger
  logic to help determine if they should be deleted or not.
  
Options:
  --name TEXT                    Name filter used to match against snapshots
                                 targeted.

  --delete_older_than_date TEXT  Remove all snapshots older than this date.
                                 Example: [2022-01-03 06:00:42.001000+00:00]

  --retain_newer_than_date TEXT  Retain all snapshots newer than this date.
                                 Example: [2022-01-03 06:00:42.001000+00:00]

  --retain_oldest                Retain the oldest snapshot.
  --retain_newest                Retain the newest snapshot.
  --retain_eol                   Retain any EOL (End of life) snapshots.
  --interactive                  No action taken until approved.
  --suppress_output              Optional to prevent the full target list.
  --limit INTEGER                Optional limit of snapshots to delete, helps
                                 for debugging.

  --help                         Show this message and exit.
```

#### Dry Run Example with Debug and verbosity output
```shell script
 docker-compose run --rm tools ec2-archives --verbose --debug --profile NamedProfileHere purge-snapshots \
   --name mongonew3 \
   --delete_older_than_date '2020-01-03 06:00:42.001000+00:00' \
   --retain_newer_than_date '2020-01-31 06:00:42.001000+00:00' \
   --retain_oldest \
   --retain_newest \
   --interactive \
   --retain_eol
```

#### Execute the purge with these filters. 
> **Please Note** Interactive mode will output all the snapshot data and ask you to confirm the delte before moving forward.

```shell script
 docker-compose run --rm tools ec2-archives --profile NamedProfileHere purge-snapshots \
   --name mongonew3 \
   --delete_older_than_date '2020-01-03 06:00:42.001000+00:00' \
   --retain_newer_than_date '2020-01-31 06:00:42.001000+00:00' \
   --retain_oldest \
   --retain_newest \
   --interactive \
   --retain_eol
```

#### `--name`` option supports regex matching
> **Please Note** All name based searches are lower-cased 
> 
```shell
  # find 
  --name "^(.)vol-" 
  --name "^(.)Example(?i)"
```