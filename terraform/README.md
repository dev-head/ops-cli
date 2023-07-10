Terraform Usage
===============

Terraform is leveraged to configure and deploy this project into AWS Lambda; with each AWS account using it's own module. The actual terraform is in a local module `modules/lambda-function`; which is customized by each parent module with specific configurations.

### Terraform Version Requirements  
* *Terraform*: `0.15.4` | `chtf 0.15.4`
* *Provider*: `aws >= 3.42`


# Build new deployable source code 
> This script is configured to save any locally created previous artifacts and then build a new archive while ignoring sensitive or data heavy directories (see script for further details).
```
./lambda/bin/build.lambda.layer.sh
```

# Test/Deploy Infrastructure through Terraform. 
> please cd into the appropriate AWS account directory before executing any make commands.

```commandline
make apply
make help
```

Functionality 
-------------
This project is hosted in an AWS Lambda function which is triggered by configured AWS EventBridge Event Rules. These events must pass a properly configured json object which allows the caller to define whatever command, arguments, and options they want to trigger. 

Initial example is provided for the Aurora archive command; permissions based around that specific need and the supporting test and production Events.


Example Resources
-----------------

## AWS account :: [example-account]
```
key_attributes = {
  "function" = {
    "arn" = "arn:aws:lambda:us-east-1:555555555555:function:example-ops-event-api"
    "log_group" = "/aws/lambda/ito-aws-event-api"
    "name" = "ito-aws-event-api"
  }
  "layer" = {
    "arn" = "arn:aws:lambda:us-east-1:555555555555:layer:codebase-example-ops-event-api:1"
    "code_size" = 13913997
    "created_at" = "2029-01-01T07:59:19.709+0000"
    "version" = "1"
  }
  "tags" = {
    "Environment" = "Prod"
    "ManagedBy" = "terraform"
    "Platform" = "Example"
  }
}
```
