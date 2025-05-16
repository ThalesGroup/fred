variable "service_account_iam_roles" {
  type = list(string)
  default = [
    "roles/artifactregistry.reader", // Docker pull permission from GKE cluster nodes
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/container.defaultNodeServiceAccount",
    "roles/artifactregistry.admin", // Ajouté pour la gestion des dépôts dans Artifact Registry
    "roles/iam.serviceAccountAdmin" // Ajouté pour la gestion des comptes de service
  ]
  description = "List of the default IAM roles to attach to the service account on the GKE Nodes."
}

resource "google_service_account" "gke_sa" {
  account_id   = "sa-${var.ENV_NAME}"
  display_name = "sa-${var.ENV_NAME}"
  description  = "GKE Security Service Account for ${var.ENV_NAME}"
  project      = var.GCP_PROJECT
}

resource "google_project_iam_member" "gke_sa_roles_association" {
  count   = length(var.service_account_iam_roles)
  project = var.GCP_PROJECT
  role    = element(var.service_account_iam_roles, count.index)
  member  = "serviceAccount:${google_service_account.gke_sa.email}"

  depends_on = [
    google_service_account.gke_sa,
  ]
}