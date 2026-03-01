# ─── Pub/Sub Module ─────────────────────────────────────────────────────────────────────
# Creates three Pub/Sub topics for asynchronous inter-service communication:
#
#   user-events    — User lifecycle events (sign-up, deletion, role change)
#   graph-updates  — Knowledge-graph mutations (node/edge upserts)
#   ai-jobs        — AI insight generation requests
#
# Each topic gets a corresponding dead-letter topic and a push subscription
# per consuming service.
# ────────────────────────────────────────────────────────────────────────────────

locals {
  topics = ["user-events", "graph-updates", "ai-jobs"]
}

# ─── Topics ──────────────────────────────────────────────────────────────────────────

resource "google_pubsub_topic" "user_events" {
  name    = "${var.environment}-user-events"
  project = var.project_id

  message_retention_duration = var.retention_duration
}

resource "google_pubsub_topic" "graph_updates" {
  name    = "${var.environment}-graph-updates"
  project = var.project_id

  message_retention_duration = var.retention_duration
}

resource "google_pubsub_topic" "ai_jobs" {
  name    = "${var.environment}-ai-jobs"
  project = var.project_id

  message_retention_duration = var.retention_duration
}

# ─── Dead-letter topics ──────────────────────────────────────────────────────────────

resource "google_pubsub_topic" "dead_letter" {
  for_each = toset(local.topics)

  name    = "${var.environment}-${each.key}-dlq"
  project = var.project_id
}

# ─── Subscriptions ────────────────────────────────────────────────────────────────────

resource "google_pubsub_subscription" "user_events_goal_service" {
  name    = "${var.environment}-user-events-goal-service"
  topic   = google_pubsub_topic.user_events.name
  project = var.project_id

  ack_deadline_seconds = var.ack_deadline_seconds

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter["user-events"].id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

resource "google_pubsub_subscription" "graph_updates_ai_service" {
  name    = "${var.environment}-graph-updates-ai-service"
  topic   = google_pubsub_topic.graph_updates.name
  project = var.project_id

  ack_deadline_seconds = var.ack_deadline_seconds

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter["graph-updates"].id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

resource "google_pubsub_subscription" "ai_jobs_ai_service" {
  name    = "${var.environment}-ai-jobs-ai-service"
  topic   = google_pubsub_topic.ai_jobs.name
  project = var.project_id

  ack_deadline_seconds = var.ack_deadline_seconds

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter["ai-jobs"].id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}
