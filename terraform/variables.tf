# ─── Project ─────────────────────────────────────────────────────────────────────────────

variable "project_id" {
  description = "GCP project ID where all resources will be created."
  type        = string

  validation {
    condition     = length(var.project_id) > 0
    error_message = "project_id must not be empty."
  }
}

variable "region" {
  description = "GCP region for primary resource deployment (e.g. us-central1)."
  type        = string
  default     = "us-central1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]+$", var.region))
    error_message = "region must be a valid GCP region string (e.g. us-central1)."
  }
}

variable "environment" {
  description = "Deployment environment: staging or production."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be either 'staging' or 'production'."
  }
}

# ─── Images ─────────────────────────────────────────────────────────────────────────────

variable "image_tag" {
  description = "Docker image tag (Git SHA) to deploy for all microservices."
  type        = string
  default     = "latest"
}

# ─── Networking ──────────────────────────────────────────────────────────────────────

variable "apps_subnet_cidr" {
  description = "CIDR range for the applications subnet."
  type        = string
  default     = "10.10.0.0/20"
}

variable "data_subnet_cidr" {
  description = "CIDR range for the data/databases subnet."
  type        = string
  default     = "10.10.16.0/20"
}

variable "management_subnet_cidr" {
  description = "CIDR range for the management subnet (bastion, tooling)."
  type        = string
  default     = "10.10.32.0/24"
}

variable "vpc_connector_cidr" {
  description = "CIDR range for the Serverless VPC Access connector."
  type        = string
  default     = "10.10.64.0/28"
}

# ─── GKE ──────────────────────────────────────────────────────────────────────────────

variable "gke_release_channel" {
  description = "GKE release channel: RAPID, REGULAR, or STABLE."
  type        = string
  default     = "REGULAR"
}

# ─── Cloud Run scaling ──────────────────────────────────────────────────────────────

variable "cloud_run_min_instances" {
  description = "Minimum number of Cloud Run instances per service (0 = scale to zero)."
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum number of Cloud Run instances per service."
  type        = number
  default     = 10
}

# ─── Storage ──────────────────────────────────────────────────────────────────────────

variable "media_bucket_location" {
  description = "GCS location for the media bucket (e.g. US, EU, ASIA)."
  type        = string
  default     = "US"
}

variable "backup_retention_days" {
  description = "Number of days to retain database backups."
  type        = number
  default     = 30
}

# ─── Monitoring & Alerts ───────────────────────────────────────────────────────────

variable "alert_email" {
  description = "Email address to receive Cloud Monitoring alert notifications."
  type        = string
  default     = ""
}

variable "error_rate_threshold" {
  description = "HTTP 5xx error rate threshold (%) that triggers an alert."
  type        = number
  default     = 5
}

variable "latency_threshold_ms" {
  description = "P99 request latency threshold (ms) that triggers an alert."
  type        = number
  default     = 2000
}

# These variables are referenced in main.tf module calls but defined here
variable "vpc_subnet_cidr" { type = string; default = "10.0.0.0/20" }
variable "vpc_pod_cidr" { type = string; default = "10.1.0.0/16" }
variable "vpc_service_cidr" { type = string; default = "10.2.0.0/16" }
variable "gke_node_count" { type = number; default = 1 }
variable "gke_machine_type" { type = string; default = "n1-standard-2" }
variable "gke_disk_size_gb" { type = number; default = 50 }
variable "gke_preemptible" { type = bool; default = false }
variable "cpu_limit" { type = string; default = "1" }
variable "memory_limit" { type = string; default = "1Gi" }
variable "min_replicas" { type = number; default = 1 }
variable "max_replicas" { type = number; default = 5 }
variable "pubsub_retention_duration" { type = string; default = "86400s" }
variable "pubsub_ack_deadline" { type = number; default = 30 }
variable "storage_location" { type = string; default = "US" }
variable "storage_storage_class" { type = string; default = "STANDARD" }
variable "cpu_threshold" { type = number; default = 0.8 }
variable "memory_threshold" { type = number; default = 0.85 }
