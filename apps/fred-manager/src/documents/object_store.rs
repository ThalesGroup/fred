// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{path::Path, time::Duration};

use anyhow::{Context, Result, bail, ensure};
use aws_sdk_s3::{
    Client,
    config::{
        BehaviorVersion, Credentials, Region, RequestChecksumCalculation, retry::RetryConfig,
        timeout::TimeoutConfig,
    },
    error::ProvideErrorMetadata,
    primitives::ByteStream,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use sha2::{Digest, Sha256};
use tokio::io::AsyncReadExt;

use super::config::ContentConfig;

#[derive(Clone)]
pub struct ObjectStore {
    client: Client,
    bucket: String,
    idle: Duration,
    transfer: Duration,
}

pub struct ObjectPage {
    pub objects: Vec<(String, i64, chrono::DateTime<chrono::Utc>)>,
    pub next: Option<String>,
}

impl ObjectStore {
    /// Build one shared SDK client; credentials never travel in request URLs or DTOs.
    pub fn new(config: &ContentConfig, access: String, secret: String) -> Result<Self> {
        config.validate()?;
        ensure!(
            !access.is_empty() && !secret.is_empty(),
            "content credentials are required"
        );
        let timeout = Duration::from_secs(config.limits.s3_seconds);
        let sdk = aws_sdk_s3::Config::builder()
            .behavior_version(BehaviorVersion::latest())
            .region(Region::new(config.region.clone()))
            .endpoint_url(&config.endpoint)
            .force_path_style(config.force_path_style)
            .credentials_provider(Credentials::new(access, secret, None, None, "fred-content"))
            .retry_config(RetryConfig::standard().with_max_attempts(2))
            .timeout_config(
                TimeoutConfig::builder()
                    .connect_timeout(Duration::from_secs(3))
                    .read_timeout(timeout)
                    .operation_attempt_timeout(timeout)
                    .operation_timeout(timeout)
                    .build(),
            )
            .request_checksum_calculation(RequestChecksumCalculation::WhenRequired)
            .build();
        Ok(Self {
            client: Client::from_conf(sdk),
            bucket: config.bucket.clone(),
            idle: Duration::from_secs(config.limits.idle_seconds),
            transfer: Duration::from_secs(config.limits.transfer_seconds),
        })
    }

    /// Refuse stores whose retention semantics cannot be honored by this lifecycle.
    pub async fn validate_bucket(&self) -> Result<()> {
        let versions = self
            .client
            .get_bucket_versioning()
            .bucket(&self.bucket)
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("cannot verify content bucket versioning"))?;
        ensure!(
            versions.status().is_none(),
            "content bucket must never have versioning enabled"
        );
        match self
            .client
            .get_object_lock_configuration()
            .bucket(&self.bucket)
            .send()
            .await
        {
            Ok(output) => ensure!(
                output
                    .object_lock_configuration()
                    .and_then(|c| c.object_lock_enabled())
                    .is_none(),
                "content bucket must have Object Lock disabled"
            ),
            Err(error) => {
                let code = error
                    .as_service_error()
                    .and_then(ProvideErrorMetadata::code);
                ensure!(
                    matches!(
                        code,
                        Some(
                            "ObjectLockConfigurationNotFoundError"
                                | "NoSuchObjectLockConfiguration"
                        )
                    ),
                    "cannot verify content bucket Object Lock configuration"
                );
            }
        }
        match self
            .client
            .get_bucket_lifecycle_configuration()
            .bucket(&self.bucket)
            .send()
            .await
        {
            Ok(output) => ensure!(
                output
                    .rules()
                    .iter()
                    .all(|rule| rule.status().as_str() == "Disabled"),
                "content bucket must have no enabled lifecycle rules"
            ),
            Err(error) => ensure!(
                error
                    .as_service_error()
                    .and_then(ProvideErrorMetadata::code)
                    == Some("NoSuchLifecycleConfiguration"),
                "cannot verify content bucket lifecycle configuration"
            ),
        }
        Ok(())
    }

    /// The same attempt key always receives the same bytes, including SDK retries.
    pub async fn put_verified(
        &self,
        key: &str,
        path: &Path,
        size: i64,
        digest: &[u8; 32],
    ) -> Result<()> {
        let body = ByteStream::from_path(path)
            .await
            .context("cannot reopen upload spool")?;
        let result = self
            .client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .if_none_match("*")
            .content_length(size)
            .content_type("application/octet-stream")
            .checksum_sha256(STANDARD.encode(digest))
            .body(body)
            .send()
            .await;
        // A lost acknowledgment or 412 after retry is settled by the same integrity check.
        if let Err(error) = &result {
            tracing::warn!(
                storage_operation = "put",
                outcome = "uncertain",
                retryable = error.as_service_error().is_none(),
                "content write requires verification"
            );
        }
        self.verify(key, size, digest).await
    }

    /// Streaming read-back works even when an S3-compatible provider omits checksums.
    pub async fn verify(&self, key: &str, size: i64, digest: &[u8; 32]) -> Result<()> {
        let result = self.get(key).await?;
        ensure!(
            result.content_length() == Some(size),
            "content length mismatch"
        );
        tokio::time::timeout(self.transfer, async {
            let mut stream = result.body.into_async_read();
            let mut hash = Sha256::new();
            let mut total = 0_i64;
            let mut buffer = [0_u8; 64 * 1024];
            loop {
                let n = tokio::time::timeout(self.idle, stream.read(&mut buffer))
                    .await
                    .context("content verification stalled")?
                    .context("content verification interrupted")?;
                if n == 0 {
                    break;
                }
                total += n as i64;
                ensure!(total <= size, "content length mismatch");
                hash.update(&buffer[..n]);
            }
            let actual: [u8; 32] = hash.finalize().into();
            ensure!(
                total == size && &actual == digest,
                "content checksum mismatch"
            );
            Ok(())
        })
        .await
        .context("content verification deadline exceeded")?
    }

    pub async fn get(
        &self,
        key: &str,
    ) -> Result<aws_sdk_s3::operation::get_object::GetObjectOutput> {
        self.client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("original content is unavailable"))
    }

    pub async fn delete(&self, key: &str) -> Result<()> {
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("content cleanup failed"))?;
        Ok(())
    }

    /// A bounded inventory page; the durable cursor is advanced only after processing it.
    pub async fn list(
        &self,
        prefix: &str,
        cursor: Option<String>,
        limit: i32,
    ) -> Result<ObjectPage> {
        let result = self
            .client
            .list_objects_v2()
            .bucket(&self.bucket)
            .prefix(prefix)
            .set_continuation_token(cursor)
            .max_keys(limit)
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("content inventory unavailable"))?;
        let next = if result.is_truncated() == Some(true) {
            Some(
                result
                    .next_continuation_token()
                    .context("content inventory omitted continuation")?
                    .to_owned(),
            )
        } else {
            None
        };
        let mut objects = Vec::with_capacity(result.contents().len());
        for object in result.contents() {
            let key = object.key().context("content inventory omitted key")?;
            if !key.starts_with(prefix) {
                bail!("content inventory returned a foreign prefix");
            }
            let modified = object
                .last_modified()
                .and_then(|d| chrono::DateTime::from_timestamp(d.secs(), d.subsec_nanos()))
                .context("content inventory omitted timestamp")?;
            objects.push((
                key.to_owned(),
                object.size().context("content inventory omitted size")?,
                modified,
            ));
        }
        Ok(ObjectPage { objects, next })
    }
}
