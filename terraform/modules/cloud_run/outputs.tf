output "gateway_url" {
  value = google_cloud_run_v2_service.services["gateway"].uri
}

output "user_service_url" {
  value = google_cloud_run_v2_service.services["user-service"].uri
}

output "goal_service_url" {
  value = google_cloud_run_v2_service.services["goal-service"].uri
}

output "ai_service_url" {
  value = google_cloud_run_v2_service.services["ai-service"].uri
}

output "notification_url" {
  value = google_cloud_run_v2_service.services["notification"].uri
}

output "integration_url" {
  value = google_cloud_run_v2_service.services["integration"].uri
}

output "load_balancer_ip" {
  value = google_compute_global_address.default.address
}
