variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }

variable "location" {
  type    = string
  default = "US"
}

variable "storage_class" {
  type    = string
  default = "STANDARD"
}

variable "retention_days_exports" {
  type    = number
  default = 30
}

variable "retention_days_standard" {
  type    = number
  default = 365
}
