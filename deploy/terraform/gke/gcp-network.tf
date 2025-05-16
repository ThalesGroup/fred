resource "google_compute_network" "vpc_network" {
  name                    = "vpc-network-${var.ENV_NAME}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "vpc_subnetwork" {
  name          = "subnet-${var.ENV_NAME}"
  ip_cidr_range = var.GCP_VPC_SUBNET_CIDR
  region        = var.GCP_REGION
  network       = google_compute_network.vpc_network.name

  depends_on = [
    google_compute_network.vpc_network,
  ]
}

resource "google_compute_address" "lb_ip" {
  name   = "lb-ip-${var.ENV_NAME}"
  region = var.GCP_REGION
}

resource "google_dns_record_set" "dns_records" {
  count        = length(var.GCP_DNS_RECORDS_LIST)
  name         = "${var.GCP_DNS_RECORDS_LIST[count.index]}.${var.ENV_NAME}.${var.DOMAIN}."
  type         = "A"
  ttl          = 300
  managed_zone = var.GCP_DNS_ZONE_NAME

  rrdatas = [google_compute_address.lb_ip.address]
}