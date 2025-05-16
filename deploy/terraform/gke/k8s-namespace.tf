resource "kubernetes_namespace" "k8s_namespace" {
  metadata {
    name = "app"
  }

  depends_on = [
    google_container_node_pool.gke_node_pool
  ]
}