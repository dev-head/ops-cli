
locals {

    default_iam_policy_statements = [
        {
            effect          = "Allow"
            actions         = ["logs:PutLogEvents", "logs:CreateLogStream", "logs:CreateLogGroup"]
            resources       = [
                format("arn:aws:logs:*:*:log-group:/aws/lambda/%s:*:*", var.name),
                format("arn:aws:logs:*:*:log-group:/aws/lambda/%s:*", var.name)
            ]
            not_actions     = [], not_resources   = [], principals = [], not_principals  = [], conditions = []
        },
        {
            effect          = "Allow"
            actions         = ["rds:StartExportTask", "rds:Describe*", "rds:DeleteDBClusterSnapshot"]
            resources       = ["*"]
            not_actions     = [], not_resources   = [], principals = [], not_principals  = [], conditions = []
        },
        {
            effect          = "Allow"
            actions         = ["s3:ListBucket", "s3:GetBucketLocation"]
            resources       = ["arn:aws:s3:::*"]
            not_actions     = [], not_resources   = [], principals = [], not_principals  = [], conditions = []
        }
    ]

    iam_role_policy_statements  = concat(local.default_iam_policy_statements, var.iam_role_policy_statements)
}


module "lambda_function" {
    source          = "terraform-aws-modules/lambda/aws"
    version         = "2.1.0"

    function_name   = var.name
    description     = var.description
    handler         = "lambda_function.lambda_handler"
    runtime         = "python3.7"
    source_path     = "../../lambda/function"
    tags            = merge(var.default_tags, {"Name": var.name})
    timeout         = "300"
    layers          = [module.lambda_layer-default.lambda_layer_arn]
    create_role     = false
    attach_policy   = false
    lambda_role     = module.function-roles.key_attributes.roles.lambda_function.arn

    environment_variables = {
        Serverless = "Terraform"
    }

    depends_on = [module.function-roles]
}

# The layer consists of a package that is created by you.
module "lambda_layer-default" {
    source                  = "terraform-aws-modules/lambda/aws"
    version                 = "2.1.0"
    create_layer            = true
    layer_name              = format("codebase-%s", var.name)
    description             = format("This layer contains the code base that is leveraged by the lambda function: [%s]", var.name)
    compatible_runtimes     = ["python3.7"]
    create_package          = false
    local_existing_package  = "../../lambda/layers/deploy/ops-cli.deploy.zip"
}

module "function-roles" {
    source          = "git@github.com:dev-head/tf-module.aws.iam-role.git?ref=0.0.1"
    default_tags    = var.default_tags

    roles    = {
        lambda_function    = {
            name                            = format("sr-%s", var.name)
            description                     = format("This role is leveraged by the lambda function: [%s]", var.name)
            max_session_duration            = 1
            permissions_boundary            = ""
            attach_aws_policies             = []
            tags                            = {}
            policy_statements_for_assume_role   = [
                {
                    effect          = "Allow"
                    actions         = ["sts:AssumeRole"]
                    principals      = [{type = "Service",  identifiers = ["lambda.amazonaws.com"]}]
                    conditions      = []
                    not_actions     = [], not_principals  = [], resources = [], not_resources = []
                }
            ]
            policy_statements   = local.iam_role_policy_statements
        }
    }
}

output  "key_attributes" {
    description = "Key Attributes provides for a specific mapping of defined resource values for the lambda function; allowing for human friendly output."
    value = {
        tags    = var.default_tags
        function = {
            name        = module.lambda_function.lambda_function_name
            arn         =  module.lambda_function.lambda_function_arn
            log_group   = module.lambda_function.lambda_cloudwatch_log_group_name
        },
        layer = {
            arn         = module.lambda_layer-default.lambda_layer_arn
            created_at  = module.lambda_layer-default.lambda_layer_created_date
            version     = module.lambda_layer-default.lambda_layer_version
            code_size   = module.lambda_layer-default.lambda_layer_source_code_size
        }
    }
}
