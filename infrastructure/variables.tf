variable "project_name" {
  description = "Project name used as a prefix for shared resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}