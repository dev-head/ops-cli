Command :: Encrypt EC2 Volumes
==============================

Description 
-----------
This command takes any number of instance-id options passed and for each instance, migrate all ebs volumes to encrypted ones.

NOTE: There is no dry run access to this, please make sure you are ready when you execute it. 

### Work flow 
- Is the instance up, and not in a bad state
- Stop the instance
- For each volume
    - create an unencrypted snapshot
    - copy that snapshot to a new encrypted snapshot
    - create an encrypted volume from that encrypted snapshot
    - unmount the unencrypted volume
    - mount the encrypted volume, same device mapping.
- Passing the option `--cleanup-please` will allow the command to delete the removed volume and snapshots. Be very sure you want to do this, if something fails during the operations you may have lost all your data.

#### Example encryption command through docker.
```
docker-compose run --rm tools ec2_encrypt encrypt_instances --help
docker-compose run --rm tools ec2_encrypt --profile NamedProfileHere encrypt_instances \
    --instance-id i-abdefghijk \
    --kms-key arn:aws:kms:us-east-1:5555555555:key/aaaaaaa-bbbb-cccc-dddd-eeeeeeee
```

#### Example command through Lambda 
```
{
  "command": "ec2_encrypt",
  "function": "encrypt_instances",
  "command_options": {},
  "command_arguments": ["--verbose", "--debug"],
  "function_arguments": [],
  "function_options": {
    "--instance-id": "i-abdefghijk",
    "--kms-key": "arn:aws:kms:us-east-1:5555555555:key/aaaaaaa-bbbb-cccc-dddd-eeeeeeee",
  }
}
```