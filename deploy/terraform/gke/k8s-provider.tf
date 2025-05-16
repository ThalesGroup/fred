provider "kubernetes" {
  host  = "https://${data.google_container_cluster.gke_cluster.endpoint}"
  token = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(
    data.google_container_cluster.gke_cluster.master_auth[0].cluster_ca_certificate
  )
}