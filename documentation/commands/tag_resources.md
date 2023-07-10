Command :: Tag Resources
========================

Description 
-----------
This command was created to provide a method to tag all resources in a given AWS account. The goal here is to normalize 
against a tagging configuration, which should mirror a global tagging policy, and give support for the user to create 
tags for resources through this script. Users will be prompted if they want to modify an existing tag or save new ones. 


Notes
-----
* There is support for executing this as a dry run, with the output being generated but no tagging actually happening. 
* Caching is reduced here due to need for fresh data when we tag and leverage those new tags in other areas.
* By Default, all regions and all supported services will go through the tagging process, you can pass additional options (see below example) to limit the target services and or regions.  
* Typing `exit` or `quit` at any prompt will gracefully exit the program where it is.

#### `interactive` Command Options 
* `--services`: Optionally, define services to tag. (Passing multiple instances of --services)
* `--regions` : Optionally, define specific regions to tag. (Passing multiple instances --regions)
* `--skip-region-prompts`: This option will skip the region prompts and get right to tagging.
* `--skip-inheritable-tagging` This option will skip the inheritable tagging routine that runs after the service tagging.
* `--skip-service-tagging` This option will skip the main service tagging and execute the inheritable tagging, unless you skipped that too.
* `--expert-mode` The best way to run this, is in expert mode; mostly it just speeds things up and shows less output. 

#### Supported Services 
* `ec2`
* `rds`
* `es`
* `elasticache`
* `redshift`
* `s3'` 
* `elb`
* `ec2:asg`
* `ecr:repos`
* `efs`
* `lambda`
* `pinpoint`
* `cloudfront`


Run The Command
---------------

### Get help & List of options.
```
docker-compose run --rm tools tag_resources --verbose --debug --dry-run interactive --help 
```

### Run the `interactive` command, with full output and as a DRY RUN. 
```
docker-compose run --rm tools tag_resources --verbose --debug --dry-run interactive
```

### Run the `interactive` command, with tagging saved. (AKA run that for real)
```
docker-compose run --rm tools tag_resources --verbose --debug --dry-run interactive
```


### Run the `interactive` command, with full output, as a DRY RUN, and with a named AWS profile to use. 
> NOTE: The matching named profile (in `~/.aws/credentials`) will be used as the target Account for being tagged. 
> NOTE: profile name here is fake; please replace with your own profile for your target
 
```
docker-compose run --rm tools tag_resources \
    --profile NamedProfileHere --verbose --debug --dry-run interactive
```

### Run with options to restrict or be more specific 
```
### this will run the tagging in ec2 and elb across both us-east-1 and us-east-2 regions. 
docker-compose run --rm tools tag_resources --verbose --debug --dry-run \
    interactive --services ec2 --services elb --regions us-east-1 --regions us-east-2

### This will skip the prompts when asking if you'd like to start tagging in the next region. 
docker-compose run --rm tools tag_resources --verbose --debug --dry-run \
    interactive --skip-region-prompts
```

### A mix of examples to reference
```
docker-compose run --rm tools tag_resources --profile NamedProfileHere --verbose --debug --dry-run \
    interactive --skip-region-prompts --services rds --regions us-east-1 

# skip main service tagging and just tag the inheritable resources.
docker-compose run --rm tools tag_resources --profile NamedProfileHere --dry-run \
    interactive --skip-region-prompts --services rds --regions us-east-1 --skip-service-tagging

# skip inheritable tagging, just tag the service resources.
docker-compose run --rm tools tag_resources --profile NamedProfileHere \
    interactive --skip-region-prompts --services rds --regions us-east-1 --skip-inheritable-tagging 

# skip inheritable tagging, run es,elasticache,redshift,s3,elb service tagging resources.
docker-compose run --rm tools tag_resources --profile NamedProfileHere \
    interactive --skip-region-prompts --regions us-east-1 --skip-inheritable-tagging \
    --services es --services elasticache --services redshift --services s3 --services elb

# run a tagging test on redshift, using expert mode.
docker-compose run --rm tools tag_resources --profile NamedProfileHere --dry-run \
    interactive --skip-region-prompts --regions us-east-1 --skip-inheritable-tagging --services redshift --expert-mode
    
# run a tagging test on ecr, using expert mode.
docker-compose run --rm tools tag_resources --profile NamedProfileHere  \
    interactive --skip-region-prompts --regions us-east-1 --skip-inheritable-tagging --services ecr:repos --expert-mode    
```
