output "cluster_name" {
  value = google_container_cluster.neo4j.name
}

output "cluster_endpoint" {
  value     = google_container_cluster.neo4j.endpoint
  sensitive = true
}

output "cluster_ca_certificate" {
  value     = google_container_cluster.neo4j.master_auth[0].cluster_ca_certificate
  sensitive = true
}
