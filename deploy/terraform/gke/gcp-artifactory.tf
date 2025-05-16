data "google_project" "project" {
}

resource "google_secret_manager_secret" "artifactory_secret" {
  secret_id = "${var.GCP_DOCKER_REGISTRY_NAME}-secret-${var.ENV_NAME}"
  replication {
    user_managed {
      replicas {
        location = var.GCP_REGION
      }
    }
  }
}

// Store the service account secret value in the GCP secret
resource "google_secret_manager_secret_version" "artifactory_secret_version" {
  secret      = google_secret_manager_secret.artifactory_secret.id
  secret_data = var.GCP_DOCKER_REGISTRY_MIRROR_PASSWORD

  depends_on = [
    google_secret_manager_secret.artifactory_secret,
  ]
}

// Give permissions to the Artifact Registry Service Agent to read the secret value
// Reference: https://cloud.google.com/iam/docs/service-agents#artifact-registry-service-agent
resource "google_secret_manager_secret_iam_member" "artifactory_secret_access" {
  secret_id = google_secret_manager_secret.artifactory_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-artifactregistry.iam.gserviceaccount.com"

  depends_on = [
    data.google_project.project,
    google_secret_manager_secret.artifactory_secret,
  ]
}

// Create a remote docker registry based on Thales Digital Artifactory
resource "google_artifact_registry_repository" "artifactory_remote_repo" {
  repository_id = "${var.GCP_DOCKER_REGISTRY_NAME}-${var.ENV_NAME}"
  description   = "Remote docker registry based on ${var.GCP_DOCKER_REGISTRY_DESCRIPTION}"
  location      = var.GCP_REGION
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  remote_repository_config {
    description = var.GCP_DOCKER_REGISTRY_DESCRIPTION
    docker_repository {
      custom_repository {
        uri = var.GCP_DOCKER_REGISTRY_MIRROR_URL
      }
    }
    upstream_credentials {
      username_password_credentials {
        username                = var.GCP_DOCKER_REGISTRY_MIRROR_USERNAME
        password_secret_version = google_secret_manager_secret_version.artifactory_secret_version.name
      }
    }
  }

  depends_on = [
    google_secret_manager_secret.artifactory_secret,
    google_secret_manager_secret_version.artifactory_secret_version,
  ]
}