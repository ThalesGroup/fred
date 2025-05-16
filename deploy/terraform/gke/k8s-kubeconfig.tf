data "google_client_config" "default" {}

data "template_file" "kubeconfig" {
  template = templatefile("${path.module}/templates/kubeconfig.tpl", {
    vars = {
      cluster_name           = "k8s-${var.ENV_NAME}"
      cluster_server         = "https://${google_container_cluster.gke_cluster.endpoint}"
      cluster_ca_certificate = google_container_cluster.gke_cluster.master_auth[0].cluster_ca_certificate
      user_access_token      = kubernetes_secret.k8s_sa_token.data["token"]
    }
  })

  depends_on = [
    google_container_node_pool.gke_node_pool,
    kubernetes_secret.k8s_sa_token
  ]
}

resource "local_file" "kubeconfig" {
  content         = data.template_file.kubeconfig.rendered
  filename        = "kubeconfig"
  file_permission = "0644"

  depends_on = [
    google_container_node_pool.gke_node_pool
  ]
}