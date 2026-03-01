output "user_events_topic" {
  value = google_pubsub_topic.user_events.name
}

output "graph_updates_topic" {
  value = google_pubsub_topic.graph_updates.name
}

output "ai_jobs_topic" {
  value = google_pubsub_topic.ai_jobs.name
}
