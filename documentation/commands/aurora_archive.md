Command :: Aurora Archive
==========================

```shell script
docker-compose run --rm tools aurora_archive --profile NamedProfileHere describe-manual-snapshots
docker-compose run --rm tools aurora_archive --profile NamedProfileHere describe-active-exports
```

Export Aurora Snapshots to S3 
-----------------------------

#### Dry Run Example with Debug and verbosity output

```shell script
docker-compose run --rm tools aurora_archive \
    --profile NamedProfileHere  --verbose export-to-s3 --dry-run \
    --s3-bucket-name "example--rds-snapshot-archive" \
    --iam-role-arn "arn:aws:iam::555555555555:role/rds-s3-export-role" \
    --kms-key-id "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01"
```

#### Example Run snapshot archive queue for rds/aurora snapshots to s3

```shell script
docker-compose run --rm tools aurora_archive \
    --profile NamedProfileHere export-to-s3 \
    --s3-bucket-name "example--rds-snapshot-archive" \
    --iam-role-arn "arn:aws:iam::555555555555:role/rds-s3-export-role" \
    --kms-key-id "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01"
```

#### Poor mans daemon. 

```shell script
watch -n 300 'docker-compose run --rm tools aurora_archive --profile NamedProfileHere export-to-s3 --s3-bucket-name "example--rds-snapshot-archive" --iam-role-arn "arn:aws:iam::555555555555:role/rds-s3-export-role" --kms-key-id "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01"'
```

---

Delete Aurora Snapshots
-----------------------
* For each snapshot  
    * Has the snapshot been archived?
    * Is the snapshot greater than (60) days?

#### Dry Run Example with Debug and verbosity output
```shell script
docker-compose run --rm tools aurora_archive \
    --profile NamedProfileHere  --verbose --debug delete-snapshots --dry-run \
    --s3-bucket-name "example--rds-snapshot-archive" \
    --iam-role-arn "arn:aws:iam::555555555555:role/rds-s3-export-role" \
    --kms-key-id "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01" \
    --limit 1
```

#### Run Delete job for real
```shell script
docker-compose run --rm tools aurora_archive \
    --profile NamedProfileHere delete-snapshots \
    --s3-bucket-name "example--rds-snapshot-archive" \
    --iam-role-arn "arn:aws:iam::555555555555:role/rds-s3-export-role" \
    --kms-key-id "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01" 

```

