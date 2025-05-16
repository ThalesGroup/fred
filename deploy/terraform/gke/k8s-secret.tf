resource "kubernetes_secret" "k8s_secret_gitlab_registry_creds" {
  metadata {
    name      = "gitlab-registry-creds"
    namespace = "app"
  }
  type = "kubernetes.io/dockerconfigjson"
  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        tostring(var.CI_REGISTRY) = {
          "username" = var.CI_DEPLOY_USER
          "password" = var.CI_DEPLOY_PASSWORD
          "auth"     = base64encode("${var.CI_DEPLOY_USER}:${var.CI_DEPLOY_PASSWORD}")
        }
      }
    })
  }

  depends_on = [
    kubernetes_namespace.k8s_namespace
  ]
}

resource "kubernetes_secret" "k8s_secret_openai_api_key" {
  metadata {
    name      = "fred-backend-openai-api-key"
    namespace = "app"
  }
  type = "Opaque"
  data = {
    "OPENAI_API_KEY" = var.OPENAI_API_KEY
  }

  depends_on = [
    kubernetes_namespace.k8s_namespace
  ]
}

resource "kubernetes_secret" "k8s_secret_kubeconfig" {
  metadata {
    name      = "fred-backend-kubeconfig"
    namespace = "app"
  }
  type = "Opaque"
  data = {
    "config" = local_file.kubeconfig.content
  }

  depends_on = [
    kubernetes_namespace.k8s_namespace,
    local_file.kubeconfig
  ]
}