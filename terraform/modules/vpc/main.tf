# ─── VPC Module ────────────────────────────────────────────────────────────────────────────
# Creates:
#   - Custom VPC network (no default subnets)
#   - 3 regional subnets (apps, services, data)
#   - Cloud NAT for egress from private nodes
#   - Firewall rules (allow internal, deny external to data tier)
# ────────────────────────────────────────────────────────────────────────────────

resource "google_compute_network" "zensensei" {
  name                    = "${var.environment}-zensensei-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "apps" {
  name          = "${var.environment}-apps"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.zensensei.id
  ip_cidr_range = var.subnet_cidr

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pod_cidr
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.service_cidr
  }

  private_ip_google_access = true
}

# ─── Cloud NAT ────────────────────────────────────────────────────────────────────────

resource "google_compute_router" "nat_router" {
  name    = "${var.environment}-nat-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.zensensei.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.environment}-cloud-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.nat_router.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ─── Firewall rules ───────────────────────────────────────────────────────────────────

resource "google_compute_firewall" "allow_internal" {
  name    = "${var.environment}-allow-internal"
  project = var.project_id
  network = google_compute_network.zensensei.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = [
    var.subnet_cidr,
    var.pod_cidr,
    var.service_cidr,
  ]
  priority = 1000
}

resource "google_compute_firewall" "deny_external_data" {
  name    = "${var.environment}-deny-external-data"
  project = var.project_id
  network = google_compute_network.zensensei.name

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["data-tier"]
  priority      = 500
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${var.environment}-allow-health-checks"
  project = var.project_id
  network = google_compute_network.zensensei.name

  allow {
    protocol = "tcp"
  }

  source_ranges = [
    "35.191.0.0/16",  # GCP health check range 1
    "130.211.0.0/22", # GCP health check range 2
  ]
  priority = 900
}
