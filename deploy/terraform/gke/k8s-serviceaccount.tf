resource "kubernetes_service_account" "k8s_sa" {
  metadata {
    name      = "fred-sa"
    namespace = "kube-system"
  }

  depends_on = [
    google_container_node_pool.gke_node_pool
  ]
}

resource "kubernetes_cluster_role_binding" "k8s_sa_view_binding" {
  metadata {
    name = "fred-sa-clusterrolebinding"
  }
  subject {
    kind      = "ServiceAccount"
    name      = "fred-sa"
    namespace = "kube-system"
  }
  role_ref {
    kind      = "ClusterRole"
    name      = "view"
    api_group = "rbac.authorization.k8s.io"
  }

  depends_on = [
    kubernetes_service_account.k8s_sa
  ]
}

resource "kubernetes_secret" "k8s_sa_token" {
  metadata {
    name      = "fred-sa-token"
    namespace = "kube-system"
    annotations = {
      "kubernetes.io/service-account.name" = "fred-sa"
    }
  }
  type = "kubernetes.io/service-account-token"

  depends_on = [
    kubernetes_service_account.k8s_sa
  ]
}