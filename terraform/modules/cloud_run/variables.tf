variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" {
  type    = string
  default = "staging"
}
variable "cpu_limit" { type = string }
variable "memory_limit" { type = string }
variable "min_replicas" { type = number }
variable "max_replicas" { type = number }
