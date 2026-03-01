# ─── Staging Environment ────────────────────────────────────────────────────────────────────────
# Apply with:
#   cd terraform
#   terraform workspace select staging
#   terraform apply -var-file=environments/staging/terraform.tfvars
# ────────────────────────────────────────────────────────────────────────────────

project_id  = "zensensei-staging"
region      = "us-central1"
environment = "staging"

# Cloud Run
cpu_limit    = "1"
memory_limit = "1Gi"
min_replicas = 1
max_replicas = 5

# GKE
gke_node_count    = 1
gke_machine_type  = "n1-standard-2"
gke_disk_size_gb  = 50
gke_preemptible   = true

# Pub/Sub
pubsub_retention_duration = "86400s"   # 1 day
pubsub_ack_deadline       = 30

# Storage
storage_location       = "US"
storage_storage_class  = "STANDARD"

# Monitoring
alert_email = "dev@zensensei.io"
error_rate_threshold    = 0.05
latency_threshold_ms    = 1000
cpu_threshold           = 0.9
memory_threshold        = 0.9

# VPC
vpc_subnet_cidr   = "10.10.0.0/20"
vpc_pod_cidr      = "10.11.0.0/16"
vpc_service_cidr  = "10.12.0.0/16"
