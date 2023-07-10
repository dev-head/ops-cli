# Variables provided 

variable "name" {
    description = "Give your function a name."
    type        = string
}

variable "default_tags" {
    description = "Map of tags to apply to resources"
    type        = any
}

variable "description" {
    description = "Tell the world why your function exists."
    type        = string
    default     = ""
}

variable "iam_role_policy_statements" {
    description = "(Optional) Provide a list of policy statement objects to be included in the lambda IAM role."
    type = list(object(
        {
            actions         = list(string)
            not_actions     = list(string)
            effect          = string
            resources       = list(string)
            not_resources   = list(string)
            principals      = list(object({
                type        = string
                identifiers = list(string)
            }))
            not_principals  = list(object({
                type        = string
                identifiers = list(string)
            }))
            conditions  = list(object({
                test    = string
                variable = string
                    values  = list(string)
            }))
        }
    ))
}
