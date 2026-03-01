# ─── Production Environment ───────────────────────────────────────────────────────────────────────
# Apply with:
#   cd terraform
#   terraform workspace select production
#   terraform apply -var-file=environments/production/terraform.tfvars
# ────────────────────────────────────────────────────────────────────────────────

project_id  = "zensensei-prod"
region      = "us-central1"
environment = "production"

# Cloud Run
cpu_limit    = "2"
memory_limit = "2Gi"
min_replicas = 2
max_replicas = 20

# GKE
gke_node_count    = 3
gke_machine_type  = "n2-standard-4"
gke_disk_size_gb  = 100
gke_preemptible   = false

# Pub/Sub
pubsub_retention_duration = "604800s"   # 7 days
pubsub_ack_deadline       = 60

# Storage
storage_location       = "US"
storage_storage_class  = "STANDARD"

# Monitoring
alert_email = "ops@zensensei.io"
error_rate_threshold    = 0.01
latency_threshold_ms    = 500
cpu_threshold           = 0.8
memory_threshold        = 0.85

# VPC
vpc_subnet_cidr   = "10.0.0.0/20"
vpc_pod_cidr      = "10.1.0.0/16"
vpc_service_cidr  = "10.2.0.0/16"
