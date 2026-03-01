output "media_bucket_name" {
  value = google_storage_bucket.buckets["media"].name
}

output "backups_bucket_name" {
  value = google_storage_bucket.buckets["backups"].name
}

output "exports_bucket_name" {
  value = google_storage_bucket.buckets["exports"].name
}
