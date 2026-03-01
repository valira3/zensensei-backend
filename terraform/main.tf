terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }

  # Remote state in GCS – bucket created out-of-band by the bootstrap script.
  backend "gcs" {
    bucket = "zensensei-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

module "vpc" {
  source = "./modules/vpc"

  project_id   = var.project_id
  region       = var.region
  environment  = var.environment
  subnet_cidr  = var.vpc_subnet_cidr
  pod_cidr     = var.vpc_pod_cidr
  service_cidr = var.vpc_service_cidr
}

module "gke" {
  source = "./modules/gke"

  project_id   = var.project_id
  region       = var.region
  environment  = var.environment
  network      = module.vpc.network_name
  subnetwork   = module.vpc.subnetwork_name
  node_count   = var.gke_node_count
  machine_type = var.gke_machine_type
  disk_size_gb = var.gke_disk_size_gb
  preemptible  = var.gke_preemptible
}

module "cloud_run" {
  source = "./modules/cloud_run"

  project_id   = var.project_id
  region       = var.region
  environment  = var.environment
  cpu_limit    = var.cpu_limit
  memory_limit = var.memory_limit
  min_replicas = var.min_replicas
  max_replicas = var.max_replicas
}

module "pubsub" {
  source = "./modules/pubsub"

  project_id                 = var.project_id
  environment                = var.environment
  retention_duration         = var.pubsub_retention_duration
  ack_deadline_seconds       = var.pubsub_ack_deadline
}

module "storage" {
  source = "./modules/storage"

  project_id     = var.project_id
  environment    = var.environment
  location       = var.storage_location
  storage_class  = var.storage_storage_class
}

module "monitoring" {
  source = "./modules/monitoring"

  project_id           = var.project_id
  environment          = var.environment
  alert_email          = var.alert_email
  error_rate_threshold = var.error_rate_threshold
  latency_threshold_ms = var.latency_threshold_ms
  cpu_threshold        = var.cpu_threshold
  memory_threshold     = var.memory_threshold
}
