terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.51.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.36.0"
    }
    template = {
      source  = "hashicorp/template"
      version = ">= 2.2.0"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.5.2"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.1.0"
    }
  }
  backend "gcs" {
  }
}