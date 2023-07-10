#-{Configure}-----------------------------------------------------------------#
terraform {
    required_providers {
        aws = {
            source  = "hashicorp/aws"
            version = ">= 3.42"
        }
    }
}


provider "aws" {
    region  = var.aws_region
    profile = var.aws_profile
}

#-{Data}--------------------------------------------------------------------#
data "aws_caller_identity" "current" {}

#-{Variables}--------------------------------------------------------------------#
variable "aws_region" {
    description = "Requried, AWS region for this to be applied to."
    type        = string
}

variable "aws_profile" {
    description = "Optional, Provider AWS profile name for local aws cli configuration."
    type        = string
    default     = ""
}
#-{Module}--------------------------------------------------------------------#
module "lambda_function" {
    source      = "../modules/lambda-function"
    name        = "example-ops-event-api"
    default_tags    = {
        Platform    = "Example"
        Environment = "Prod"
        ManagedBy   = "Terraform"
    }

    iam_role_policy_statements = [
        {
            effect          = "Allow"
            actions         = ["kms:Decrypt",  "kms:Encrypt",  "kms:ListAliases",  "kms:GenerateDataKey",  "kms:ReEncryptTo",  "kms:DescribeKey",  "kms:GenerateDataKeyPairWithoutPlaintext",  "kms:ListResourceTags",  "kms:RetireGrant",  "kms:ReEncryptFrom",  "kms:ListGrants",  "kms:CreateGrant"]
            resources       = ["arn:aws:kms:us-east-1:555555555555:key/5555555-555555-55555-5555"]
            not_actions     = [], not_resources   = [], principals = [], not_principals  = [], conditions = []
        },
        {
            effect          = "Allow"
            actions         = ["iam:PassRole"]
            resources       = ["arn:aws:iam::555555555555:role/rds-s3-export-role"]
            not_actions     = [], not_resources   = [], principals = [], not_principals  = [], conditions = []
        },
        {
            effect          = "Allow"
            actions         = ["s3:PutObject*", "s3:GetObject*", "s3:DeleteObject*"]
            resources       = ["arn:aws:s3:::example--rds-snapshot-archive/*"]
            not_actions     = [], not_resources   = [], principals = [], not_principals  = [], conditions = []
        }
    ]
    description = "This function provides automations and abstractions to the aws api using events."
}

#-{Event|Hello World Testing}------------------------------------------------------------------------#
resource "aws_cloudwatch_event_rule" "hello-world" {
    name                = format("%s--hello-world", module.lambda_function.key_attributes.function.name)
    description         = format("Run Hello World on Lambda function [%s]", module.lambda_function.key_attributes.function.name)
    schedule_expression = "rate(1 minute)"
    is_enabled          = false
    tags                = module.lambda_function.key_attributes.tags
    depends_on          = [module.lambda_function]
}

resource "aws_cloudwatch_event_target" "hello-world" {
    arn  = module.lambda_function.key_attributes.function.arn
    rule = aws_cloudwatch_event_rule.hello-world.id
    input = jsonencode({
        "command"               = "example",
        "function"              = "hello",
        "command_options"       = {},
        "command_arguments"     = [],
        "function_arguments"    = ["Martha", "Snoopy"],
        "function_options"      = {}
    })
}

resource "aws_lambda_permission" "hello-world" {
    statement_id  = "AllowInvokeEvent--hello-world"
    source_arn    = aws_cloudwatch_event_rule.hello-world.arn
    action        = "lambda:InvokeFunction"
    function_name = module.lambda_function.key_attributes.function.name
    principal     = "events.amazonaws.com"
}

#-{Event|Export Aurora snapshots to S3|Dryrun|Testing}------------------------------------------------------------------------#
resource "aws_cloudwatch_event_rule" "rds-archive-export-to-s3-dryrun" {
    name                = format("%s--rds-archive-export-to-s3-dryrun", module.lambda_function.key_attributes.function.name)
    description         = format("Run RDS Archive Dry RUN! on Lambda function [%s]", module.lambda_function.key_attributes.function.name)
    schedule_expression = "rate(2 minutes)"
    is_enabled          = false
    tags                = module.lambda_function.key_attributes.tags
    depends_on          = [module.lambda_function]
}

resource "aws_cloudwatch_event_target" "rds-archive-export-to-s3-dryrun" {
    rule = aws_cloudwatch_event_rule.rds-archive-export-to-s3-dryrun.id
    arn  = module.lambda_function.key_attributes.function.arn
    input = jsonencode({
        "command"= "aurora_archive",
        "function"= "export-to-s3",
        "command_options"= {},
        "command_arguments"= ["--verbose", "--debug"],
        "function_arguments"= ["--dry-run"],
        "function_options"= {
            "--s3-bucket-name"= "example--rds-snapshot-archive",
            "--iam-role-arn"= "arn:aws:iam::555555555555:role/rds-s3-export-role",
            "--kms-key-id"= "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01"
        }
    })
}

resource "aws_lambda_permission" "rds-archive-export-to-s3-dryrun" {
    statement_id  = "AllowInvokeEvent--rds-archive-export-to-s3-dryrun"
    source_arn    = aws_cloudwatch_event_rule.rds-archive-export-to-s3-dryrun.arn
    action        = "lambda:InvokeFunction"
    function_name = module.lambda_function.key_attributes.function.name
    principal     = "events.amazonaws.com"
}

#-{Event|Export Aurora snapshots to S3|Deployed}------------------------------------------------------------------------#
resource "aws_cloudwatch_event_rule" "rds-archive-export-to-s3" {
    name                = format("%s--rds-archive-export-to-s3", module.lambda_function.key_attributes.function.name)
    description         = format("Sync RDS snapshots to S3 [example--rds-snapshot-archive] using Lambda function [%s]", module.lambda_function.key_attributes.function.name)
    schedule_expression = "rate(10 hours)"
    is_enabled          = false
    tags                = module.lambda_function.key_attributes.tags
    depends_on          = [module.lambda_function]
}

resource "aws_cloudwatch_event_target" "rds-archive-export-to-s3" {
    arn  = module.lambda_function.key_attributes.function.arn
    rule = aws_cloudwatch_event_rule.rds-archive-export-to-s3.id
    input = jsonencode({
        "command"= "aurora_archive",
        "function"= "export-to-s3",
        "command_options"= {},
        "command_arguments"= [],
        "function_arguments"= [],
        "function_options"= {
            "--s3-bucket-name"= "example--rds-snapshot-archive",
            "--iam-role-arn"= "arn:aws:iam::555555555555:role/rds-s3-export-role",
            "--kms-key-id"= "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01"
        }
    })
}

resource "aws_lambda_permission" "rds-archive-export-to-s3" {
    statement_id  = "AllowInvokeEvent--rds-archive-export-to-s3"
    source_arn    = aws_cloudwatch_event_rule.rds-archive-export-to-s3.arn
    action        = "lambda:InvokeFunction"
    function_name = module.lambda_function.key_attributes.function.name
    principal     = "events.amazonaws.com"
}

#-{Event|RDS Snapshot Pruning|Dry Run|Testing}------------------------------------------------------------------------#
resource "aws_cloudwatch_event_rule" "rds-archive-delete-snapshots-dryrun" {
    name                = format("%s--rds-archive-delete-snapshots-dryrun", module.lambda_function.key_attributes.function.name)
    description         = format("Delete Snapshots that have been archived. Dry RUN! on Lambda function [%s]", module.lambda_function.key_attributes.function.name)
    schedule_expression = "rate(2 minutes)"
    is_enabled          = false
    tags                = module.lambda_function.key_attributes.tags
    depends_on          = [module.lambda_function]
}

resource "aws_cloudwatch_event_target" "rds-archive-delete-snapshots-dryrun" {
    arn  = module.lambda_function.key_attributes.function.arn
    rule = aws_cloudwatch_event_rule.rds-archive-delete-snapshots-dryrun.id
    input = jsonencode({
        "command"= "aurora_archive",
        "function"= "delete-snapshots",
        "command_options"= {},
        "command_arguments"= [],
        "function_arguments"= ["--dry-run"],
        "function_options": {
            "--s3-bucket-name"= "example--rds-snapshot-archive",
            "--iam-role-arn"= "arn:aws:iam::555555555555:role/rds-s3-export-role",
            "--kms-key-id"= "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01",
            "--limit": 100
        }
    })
}

resource "aws_lambda_permission" "rds-archive-delete-snapshots-dryrun" {
    statement_id  = "AllowInvokeEvent--rds-archive-delete-snapshots-dryrun"
    source_arn    = aws_cloudwatch_event_rule.rds-archive-delete-snapshots-dryrun.arn
    action        = "lambda:InvokeFunction"
    function_name = module.lambda_function.key_attributes.function.name
    principal     = "events.amazonaws.com"
}

#-{Event|RDS Snapshot Pruning|Deployed}------------------------------------------------------------------------#
resource "aws_cloudwatch_event_rule" "rds-archive-delete-snapshots" {
    name                = format("%s--rds-archive-delete-snapshots", module.lambda_function.key_attributes.function.name)
    description         = format("Delete Snapshots that have been archived on Lambda function [%s]", module.lambda_function.key_attributes.function.name)
    schedule_expression = "rate(11 hours)"
    is_enabled          = false
    tags                = module.lambda_function.key_attributes.tags
    depends_on          = [module.lambda_function]
}

resource "aws_cloudwatch_event_target" "rds-archive-delete-snapshots" {
    rule = aws_cloudwatch_event_rule.rds-archive-delete-snapshots.id
    arn  = module.lambda_function.key_attributes.function.arn
    input = jsonencode({
        "command"= "aurora_archive",
        "function"= "delete-snapshots",
        "command_options"= {},
        "command_arguments"= [],
        "function_arguments"= [],
        "function_options": {
            "--s3-bucket-name"= "example--rds-snapshot-archive",
            "--iam-role-arn"= "arn:aws:iam::555555555555:role/rds-s3-export-role",
            "--kms-key-id"= "arn:aws:kms:us-east-1:555555555555:alias/archive-rds-v01",
            "--limit": 100
        }
    })
}

resource "aws_lambda_permission" "rds-archive-delete-snapshots" {
    statement_id  = "AllowInvokeEvent--rds-archive-delete-snapshots"
    source_arn    = aws_cloudwatch_event_rule.rds-archive-delete-snapshots.arn
    action        = "lambda:InvokeFunction"
    function_name = module.lambda_function.key_attributes.function.name
    principal     = "events.amazonaws.com"
}


#-{Outputs}--------------------------------------------------------------------#
output "caller_data" {
    value = data.aws_caller_identity.current
}

output "key_attributes" { value = module.lambda_function.key_attributes }