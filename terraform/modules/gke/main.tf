# ─── GKE Module ────────────────────────────────────────────────────────────────────────────
# Creates a GKE Autopilot cluster to host Neo4j (graph database).
# Autopilot is chosen to minimize operational overhead; node pools are
# managed automatically by GKE.
# ────────────────────────────────────────────────────────────────────────────────

resource "google_container_cluster" "neo4j" {
  name     = "${var.environment}-neo4j-cluster"
  location = var.region
  project  = var.project_id

  enable_autopilot = true

  network    = var.network
  subnetwork = var.subnetwork

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  release_channel {
    channel = "REGULAR"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
  }

  lifecycle {
    ignore_changes = [
      node_config,
    ]
  }
}

# ─── Neo4j StatefulSet via Helm ──────────────────────────────────────────────────────────
# Deploying Neo4j via the official Helm chart is handled separately in
# the k8s/ directory.  The Terraform resources here only provision the
# cluster and expose the necessary service-account / RBAC bindings.
# ────────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "neo4j" {
  account_id   = "neo4j-sa"
  display_name = "Neo4j Service Account"
  project      = var.project_id
}

resource "google_project_iam_member" "neo4j_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.neo4j.email}"
}

resource "google_service_account_iam_binding" "workload_identity" {
  service_account_id = google_service_account.neo4j.name
  role               = "roles/iam.workloadIdentityUser"

  members = [
    "serviceAccount:${var.project_id}.svc.id.goog[neo4j/neo4j]",
  ]
}
