# Deployment Configuration

This directory contains Docker Compose files and supporting configuration used for **local development and testing only**.

## Certificate Notice

The certificates located under this folder and sub folders
are **self-signed and non-sensitive**. They are used **only to enable TLS communication** between containers (e.g., OpenSearch and dashboards) in local environments.

- These certificates are:
  - Auto-generated or manually created for test purposes.
  - Not valid for production use.
  - Not associated with any real domains or private credentials.

## Reminder

These files are included to support development workflows such as:

- Running OpenSearch with HTTPS in Docker Compose
- Avoiding mixed-content issues when using local dashboards
- Enabling local testing of TLS scenarios

Do **not** reuse these certificates or keys in production. For real deployments, proper certificate management and secret handling must be enforced.

## Contact

For any security or deployment-related concerns, please reach out via the [Fred GitHub repository](https://github.com/ThalesGroup/fred).
