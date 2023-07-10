Command :: EC2 Run Plan
=======================

This command is used to run plans against one or more EC2 instances. A plan can consist of uploading one or more files and running one or more commands, per EC2 instance. You can define a custom filter, in a yaml file, to specify your targets to run a plan against.

Running a plan requires us to find all matching target EC2 descriptions and then find a valid ssh key for each one. We do this to ensure we can run a plan against a given instance without worrying about custom ssh keys for each one, just place valid ones in `data/ssh-keys` and any *.priv keys will be used to test for ssh access. Due to this requirement of a cached file we have a `--cache_ttl` option with a Default of 43200 seconds (1 Day), you can override that with the `--cache_ttl` option to modify the timeout or you can force it to rebuild by passing the `--rebuild_cache` option.  

#### SSH Access Required
> Please copy your ssh keys here
```
cp -R ~/.ssh/*.priv data/ssh-keys/
cp -R ~/.ssh/aws/*.priv data/ssh-keys/
```


#### Usage
```commandline
docker-compose run --rm tools ec2 run-plan --help
```

#### Example plan 
```commandline

docker-compose run --rm tools ec2 --profile NamedProfileHere run-plan \
    --plan plans/example.yml \
    --filters filters/ec2.active.yml \
    --output log/example-ec2.instance_store.log
    
    
docker-compose run --rm tools ec2 --profile NamedProfileHere run-plan \
    --plan plans/aws-cert-bundles.yml \
    --filters filters/ec2.test.yml


docker-compose run --rm tools ec2 --profile NamedProfileHere run-plan \
    --plan plans/apt-get-update.yml \
    --filters filters/ec2.active.yml \
    --output log/apt-get-update.results.log
```