resource "google_container_cluster" "gke_cluster" {
  name                     = "k8s-${var.ENV_NAME}"
  location                 = var.GCP_ZONE
  remove_default_node_pool = true
  initial_node_count       = 1
  network                  = google_compute_network.vpc_network.name
  subnetwork               = google_compute_subnetwork.vpc_subnetwork.name
  deletion_protection      = false
}

// It is recommended that node pools be created and managed as separate resources
// This allows node pools to be added and removed without recreating the cluster
resource "google_container_node_pool" "gke_node_pool" {
  count      = var.GCP_GKE_NODE_COUNT > 0 ? 1 : 0
  name       = "node-pool-k8s-${var.ENV_NAME}"
  location   = var.GCP_ZONE
  cluster    = google_container_cluster.gke_cluster.name
  node_count = var.GCP_GKE_NODE_COUNT

  node_config {
    // Google recommends custom service accounts that have cloud-platform scope and permissions granted via IAM Roles
    // Use the service account created for the cluster
    service_account = google_service_account.gke_sa.email
    // Set default scopes
    oauth_scopes = [
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/servicecontrol",
      "https://www.googleapis.com/auth/trace.append",
    ]
    machine_type = var.GCP_GKE_NODE_TYPE
    preemptible  = false

    // Enable NVIDIA Collective Communication Library (NCCL) Fast Socket plugin (mandatory when using GPU sharding)
    fast_socket {
      enabled = true
    }

    // Enable gVNIC (alternative to the virtIO-based ethernet driver) to be able to use NCCL Fast Socket
    gvnic {
      enabled = true
    }

    // GPU configuration
    guest_accelerator {
      count = var.GCP_GKE_GPU_COUNT
      type  = var.GCP_GKE_GPU_TYPE
      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }
  }

  depends_on = [
    google_container_cluster.gke_cluster,
  ]
}

data "google_container_cluster" "gke_cluster" {
  name     = google_container_cluster.gke_cluster.name
  location = google_container_cluster.gke_cluster.location
}