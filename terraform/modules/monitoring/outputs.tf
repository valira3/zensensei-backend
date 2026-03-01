output "dashboard_name" {
  value = google_monitoring_dashboard.zensensei.id
}

output "uptime_check_id" {
  value = google_monitoring_uptime_check_config.gateway_health.uptime_check_id
}

output "notification_channel_id" {
  value = google_monitoring_notification_channel.email.id
}
