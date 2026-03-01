variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "network" { type = string }
variable "subnetwork" { type = string }

variable "node_count" { type = number; default = 1 }
variable "machine_type" { type = string; default = "n1-standard-2" }
variable "disk_size_gb" { type = number; default = 50 }
variable "preemptible" { type = bool; default = false }
