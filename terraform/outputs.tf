# ─── Cloud Run Service URLs ──────────────────────────────────────────────────────────────────

output "gateway_url" {
  description = "Public HTTPS URL for the API gateway."
  value       = module.cloud_run.gateway_url
}

output "user_service_url" {
  description = "Internal URL for the user service."
  value       = module.cloud_run.user_service_url
  sensitive   = true
}

output "goal_service_url" {
  description = "Internal URL for the goal service."
  value       = module.cloud_run.goal_service_url
  sensitive   = true
}

output "ai_service_url" {
  description = "Internal URL for the AI service."
  value       = module.cloud_run.ai_service_url
  sensitive   = true
}

output "notification_url" {
  description = "Internal URL for the notification service."
  value       = module.cloud_run.notification_url
  sensitive   = true
}

output "integration_url" {
  description = "Internal URL for the integration service."
  value       = module.cloud_run.integration_url
  sensitive   = true
}

# ─── GKE ───────────────────────────────────────────────────────────────────────────────

output "neo4j_cluster_name" {
  description = "GKE cluster name for Neo4j."
  value       = module.gke.cluster_name
}

output "neo4j_cluster_endpoint" {
  description = "GKE cluster API endpoint for Neo4j."
  value       = module.gke.cluster_endpoint
  sensitive   = true
}

# ─── Pub/Sub ────────────────────────────────────────────────────────────────────────

output "pubsub_user_events_topic" {
  description = "Pub/Sub topic for user lifecycle events."
  value       = module.pubsub.user_events_topic
}

output "pubsub_graph_updates_topic" {
  description = "Pub/Sub topic for knowledge-graph mutations."
  value       = module.pubsub.graph_updates_topic
}

output "pubsub_ai_jobs_topic" {
  description = "Pub/Sub topic for AI insight generation jobs."
  value       = module.pubsub.ai_jobs_topic
}

# ─── Storage ─────────────────────────────────────────────────────────────────────────

output "media_bucket" {
  description = "GCS bucket for user-uploaded media."
  value       = module.storage.media_bucket_name
}

output "backups_bucket" {
  description = "GCS bucket for database backups."
  value       = module.storage.backups_bucket_name
}

output "exports_bucket" {
  description = "GCS bucket for data exports."
  value       = module.storage.exports_bucket_name
}

# ─── Networking ─────────────────────────────────────────────────────────────────────

output "vpc_network_name" {
  description = "VPC network name."
  value       = module.vpc.network_name
}

output "vpc_subnetwork_name" {
  description = "Primary subnetwork name."
  value       = module.vpc.subnetwork_name
}

output "load_balancer_ip" {
  description = "Static IP address of the external HTTPS load balancer."
  value       = module.cloud_run.load_balancer_ip
}
