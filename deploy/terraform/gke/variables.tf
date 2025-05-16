variable "DOMAIN" {
  type        = string
  description = "Environment name used as suffix to identify resources"
  default     = "my-domain.local"
}

variable "ENV_NAME" {
  type        = string
  description = "Environment name used as suffix to identify resources"
  default     = "ci"
}

variable "GCP_REGION" {
  type        = string
  description = "Google Cloud region"
  default     = "europe-west4"
}

variable "GCP_ZONE" {
  type        = string
  description = "Google Cloud region zone"
  default     = "europe-west4-a"
}

variable "GCP_PROJECT" {
  type        = string
  description = "Google Cloud project ID"
  default     = "my-project"
}

variable "GCP_VPC_SUBNET_CIDR" {
  type        = string
  description = "Google Cloud VPC subnet cidr"
  default     = "10.10.1.0/24"
}

variable "GCP_GKE_NODE_COUNT" {
  type        = string
  description = "Number of GKE node"
  default     = "1"
}

variable "GCP_GKE_NODE_TYPE" {
  type        = string
  description = "GKE node type"
  default     = "n1-standard-1"
}

variable "GCP_GKE_GPU_COUNT" {
  type        = string
  description = "GPU count per GKE node"
  default     = "0"
}

variable "GCP_GKE_GPU_TYPE" {
  type        = string
  description = "GPU type per GKE node"
  default     = "nvidia-tesla-t4"
}

variable "GCP_DNS_ZONE_NAME" {
  type        = string
  description = "Name of managed cloud DNS zone"
  default     = "my-dns-zone"
}

variable "GCP_DNS_RECORDS_LIST" {
  type        = list(string)
  description = "List of DNS records"
  default     = ["www1", "www2"]
}

variable "GCP_DOCKER_REGISTRY_NAME" {
  type        = string
  description = "The name of the GCP docker registry. It will be suffixed by the ENV variable"
  default     = "my-registry"
}

variable "GCP_DOCKER_REGISTRY_DESCRIPTION" {
  type        = string
  description = "A short description of the remote docker registry"
  default     = "my mirror registry"
}

variable "GCP_DOCKER_REGISTRY_MIRROR_URL" {
  type        = string
  description = "The name of the GCP docker registry. It will be suffixed by the ENV variable"
  default     = "https://index.docker.io/v1/"
}

variable "GCP_DOCKER_REGISTRY_MIRROR_USERNAME" {
  type        = string
  description = "Service account username to pull artefacts from artifactory.thalesdigital.io"
  sensitive   = true
}

variable "GCP_DOCKER_REGISTRY_MIRROR_PASSWORD" {
  type        = string
  description = "Service account token to pull artefacts from artifactory.thalesdigital.io"
  sensitive   = true
}

#
# For Gitlab CI deployment
# 

variable "CI_REGISTRY" {
  type        = string
  description = "Gitlab ci registry URL"
  sensitive   = true
}

variable "CI_DEPLOY_USER" {
  type        = string
  description = "Gitlab ci deployment user"
  sensitive   = true
}

variable "CI_DEPLOY_PASSWORD" {
  type        = string
  description = "Gitlab ci deployment user password"
  sensitive   = true
}

variable "OPENAI_API_KEY" {
  type        = string
  description = "OpenAI API Key"
  sensitive   = true
}