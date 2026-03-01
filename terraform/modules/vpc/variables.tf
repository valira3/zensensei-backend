variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }

variable "apps_subnet_cidr" {
  type    = string
  default = "10.0.0.0/20"
}
variable "subnet_cidr" { type = string }
variable "pod_cidr" { type = string }
variable "service_cidr" { type = string }
