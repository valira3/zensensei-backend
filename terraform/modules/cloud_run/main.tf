# ─── Cloud Run Module ─────────────────────────────────────────────────────────────────────
# Deploys all ZenSensei micro-services as Cloud Run v2 services.
#
# Services deployed:
#   • gateway        – Public-facing API gateway (port 8000)
#   • user-service   – Authentication & user management (port 8001)
#   • goal-service   – Goal & task management (port 8002)
#   • ai-service     – LLM orchestration & insights (port 8003)
#   • notification   – Push / e-mail / in-app notifications (port 8004)
#   • integration    – Third-party connector hub (port 8005)
# ────────────────────────────────────────────────────────────────────────────────

locals {
  services = {
    gateway = {
      image = "gcr.io/${var.project_id}/gateway:latest"
      port  = 8000
    }
    user-service = {
      image = "gcr.io/${var.project_id}/user-service:latest"
      port  = 8001
    }
    goal-service = {
      image = "gcr.io/${var.project_id}/goal-service:latest"
      port  = 8002
    }
    ai-service = {
      image = "gcr.io/${var.project_id}/ai-service:latest"
      port  = 8003
    }
    notification = {
      image = "gcr.io/${var.project_id}/notification:latest"
      port  = 8004
    }
    integration = {
      image = "gcr.io/${var.project_id}/integration:latest"
      port  = 8005
    }
  }
}

resource "google_cloud_run_v2_service" "services" {
  for_each = local.services

  name     = "${var.environment}-${each.key}"
  location = var.region
  project  = var.project_id

  template {
    scaling {
      min_instance_count = var.min_replicas
      max_instance_count = var.max_replicas
    }

    containers {
      image = each.value.image

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
        cpu_idle = true
      }

      ports {
        container_port = each.value.port
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "PORT"
        value = tostring(each.value.port)
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = each.value.port
        }
        initial_delay_seconds = 10
        period_seconds        = 30
        failure_threshold     = 3
      }

      startup_probe {
        http_get {
          path = "/health"
          port = each.value.port
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 6
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# ─── IAM: allow unauthenticated invocations on the gateway only ────────────────

resource "google_cloud_run_v2_service_iam_member" "gateway_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.services["gateway"].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Internal services: allow only the gateway SA to invoke them
resource "google_cloud_run_v2_service_iam_member" "internal_invoker" {
  for_each = {
    for k, _ in local.services : k => k
    if k != "gateway"
  }

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.services[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:gateway-sa@${var.project_id}.iam.gserviceaccount.com"
}

# ─── Load Balancer ───────────────────────────────────────────────────────────────────

resource "google_compute_global_address" "default" {
  name    = "${var.environment}-zensensei-ip"
  project = var.project_id
}

resource "google_compute_managed_ssl_certificate" "default" {
  name    = "${var.environment}-zensensei-cert"
  project = var.project_id

  managed {
    domains = ["api.zensensei.io"]
  }
}

resource "google_compute_backend_service" "gateway" {
  name    = "${var.environment}-gateway-backend"
  project = var.project_id

  backend {
    group = google_cloud_run_v2_service.services["gateway"].name
  }

  protocol    = "HTTPS"
  timeout_sec = 30
}

resource "google_compute_url_map" "default" {
  name            = "${var.environment}-zensensei-urlmap"
  project         = var.project_id
  default_service = google_compute_backend_service.gateway.id
}

resource "google_compute_target_https_proxy" "default" {
  name             = "${var.environment}-zensensei-https-proxy"
  project          = var.project_id
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_managed_ssl_certificate.default.id]
}

resource "google_compute_global_forwarding_rule" "default" {
  name       = "${var.environment}-zensensei-https-rule"
  project    = var.project_id
  target     = google_compute_target_https_proxy.default.id
  port_range = "443"
  ip_address = google_compute_global_address.default.address
}
