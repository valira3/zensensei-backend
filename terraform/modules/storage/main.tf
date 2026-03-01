# ─── Storage Module ─────────────────────────────────────────────────────────────────────
# Creates three GCS buckets:
#   - media:   User-uploaded files (avatars, attachments)
#   - backups: Database / Neo4j backups
#   - exports: Data exports requested by users
# ────────────────────────────────────────────────────────────────────────────────

locals {
  buckets = {
    media   = { suffix = "media",   versioning = false }
    backups = { suffix = "backups", versioning = true  }
    exports = { suffix = "exports", versioning = false }
  }
}

resource "google_storage_bucket" "buckets" {
  for_each = local.buckets

  name          = "${var.project_id}-${var.environment}-${each.value.suffix}"
  location      = var.location
  storage_class = var.storage_class
  project       = var.project_id

  uniform_bucket_level_access = true

  versioning {
    enabled = each.value.versioning
  }

  lifecycle_rule {
    action { type = "Delete" }
    condition {
      age                   = each.key == "exports" ? 30 : 365
      matches_storage_class = ["STANDARD"]
    }
  }

  # Block public access
  public_access_prevention = "enforced"

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ─── IAM bindings ────────────────────────────────────────────────────────────────────
# The user-service SA needs object-level access to the media bucket;
# the ai-service SA needs read/write access to exports.

resource "google_storage_bucket_iam_member" "user_service_media" {
  bucket = google_storage_bucket.buckets["media"].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:user-service-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "ai_service_exports" {
  bucket = google_storage_bucket.buckets["exports"].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:ai-service-sa@${var.project_id}.iam.gserviceaccount.com"
}
