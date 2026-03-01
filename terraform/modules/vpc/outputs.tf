output "network_name" {
  value = google_compute_network.zensensei.name
}

output "network_id" {
  value = google_compute_network.zensensei.id
}

output "subnetwork_name" {
  value = google_compute_subnetwork.apps.name
}

output "subnetwork_id" {
  value = google_compute_subnetwork.apps.id
}

output "nat_ip" {
  value = google_compute_router_nat.nat.name
}
