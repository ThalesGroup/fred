// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use anyhow::{Result, ensure};
use serde::Deserialize;
use utoipa::ToSchema;

pub const MAX_FILE_BYTES: u64 = 100 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ContentConfig {
    pub endpoint: String,
    pub bucket: String,
    #[serde(default = "region")]
    pub region: String,
    #[serde(default = "prefix")]
    pub prefix: String,
    #[serde(default = "access_key")]
    pub access_key_env_var: String,
    #[serde(default = "secret_key")]
    pub secret_key_env_var: String,
    #[serde(default)]
    pub allow_insecure: bool,
    #[serde(default = "yes")]
    pub force_path_style: bool,
    #[serde(default = "yes")]
    pub uploads_enabled: bool,
    /// Disable admission and cleanup while restoring a database/storage pair.
    #[serde(default = "yes")]
    pub cleanup_enabled: bool,
    #[serde(default = "temp_dir")]
    pub temp_dir: String,
    #[serde(default)]
    pub limits: Limits,
}

#[derive(Clone, Debug, Deserialize, ToSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Limits {
    pub file_bytes: u64,
    pub uploads: u32,
    pub downloads: u32,
    pub temp_bytes: u64,
    pub idle_seconds: u64,
    pub transfer_seconds: u64,
    pub s3_seconds: u64,
    pub personal_bytes: i64,
    pub team_bytes: i64,
    pub organization_bytes: i64,
    pub cleanup_backlog_bytes: i64,
    pub cleanup_interval_seconds: u64,
    pub cleanup_batch: u32,
    pub receipt_retention_days: u32,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            file_bytes: MAX_FILE_BYTES,
            uploads: 8,
            downloads: 8,
            temp_bytes: 8 * MAX_FILE_BYTES,
            idle_seconds: 30,
            transfer_seconds: 300,
            s3_seconds: 120,
            personal_bytes: 5 * 1024 * 1024 * 1024,
            team_bytes: 5 * 1024 * 1024 * 1024,
            organization_bytes: 5 * 1024 * 1024 * 1024,
            cleanup_backlog_bytes: 1024 * 1024 * 1024,
            cleanup_interval_seconds: 30,
            cleanup_batch: 100,
            receipt_retention_days: 7,
        }
    }
}

impl ContentConfig {
    pub fn validate(&self) -> Result<()> {
        let endpoint = reqwest::Url::parse(&self.endpoint)
            .map_err(|_| anyhow::anyhow!("content.endpoint must be an absolute HTTP(S) URL"))?;
        ensure!(
            endpoint.scheme() == "https" || (self.allow_insecure && endpoint.scheme() == "http"),
            "content.endpoint requires HTTPS (allow_insecure is for local deployments)"
        );
        ensure!(
            endpoint.host_str().is_some()
                && endpoint.username().is_empty()
                && endpoint.password().is_none()
                && endpoint.query().is_none()
                && endpoint.fragment().is_none()
                && endpoint.path() == "/",
            "content.endpoint must not contain credentials, a path, query or fragment"
        );
        ensure!(
            (3..=63).contains(&self.bucket.len())
                && self.bucket.bytes().all(|b| b.is_ascii_lowercase()
                    || b.is_ascii_digit()
                    || b == b'-'
                    || b == b'.'),
            "content.bucket must be an S3 bucket name"
        );
        ensure!(
            !self.prefix.is_empty()
                && self.prefix.len() <= 128
                && self
                    .prefix
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_'),
            "content.prefix must be a single nonempty namespace label"
        );
        for value in [
            &self.region,
            &self.access_key_env_var,
            &self.secret_key_env_var,
        ] {
            ensure!(
                !value.is_empty() && value.len() <= 128 && !value.chars().any(char::is_whitespace),
                "content region and secret references must be nonblank bounded identifiers"
            );
        }
        ensure!(
            std::path::Path::new(&self.temp_dir).is_absolute(),
            "content.temp_dir must be absolute"
        );
        let l = &self.limits;
        ensure!(
            (1..=MAX_FILE_BYTES).contains(&l.file_bytes),
            "content file limit must be 1..100 MiB"
        );
        ensure!(
            (1..=64).contains(&l.uploads) && (1..=64).contains(&l.downloads),
            "content concurrency must be 1..64"
        );
        ensure!(
            l.temp_bytes >= l.file_bytes * u64::from(l.uploads)
                && l.temp_bytes <= 64 * MAX_FILE_BYTES,
            "content temporary budget must cover all admitted uploads and remain at most 6400 MiB"
        );
        ensure!(
            (1..=60).contains(&l.idle_seconds)
                && (l.idle_seconds..=600).contains(&l.transfer_seconds),
            "content transfer deadlines must be finite and cover the idle deadline"
        );
        ensure!(
            (1..=300).contains(&l.s3_seconds),
            "content S3 deadline must be 1..300 seconds"
        );
        ensure!(
            [
                l.personal_bytes,
                l.team_bytes,
                l.organization_bytes,
                l.cleanup_backlog_bytes
            ]
            .iter()
            .all(|&n| n > 0),
            "content quotas and cleanup budget must be positive"
        );
        ensure!(
            (1..=300).contains(&l.cleanup_interval_seconds)
                && (1..=1000).contains(&l.cleanup_batch),
            "content cleanup interval/batch are outside supported bounds"
        );
        ensure!(
            (1..=30).contains(&l.receipt_retention_days),
            "content receipt retention must be 1..30 days"
        );
        ensure!(
            self.cleanup_enabled || !self.uploads_enabled,
            "content uploads must be disabled while cleanup is suspended"
        );
        Ok(())
    }
}

impl Limits {
    /// A crash expires after all bounded remote work and final authorization could finish.
    pub fn lease_seconds(&self) -> i64 {
        (2 * self.s3_seconds + self.transfer_seconds + 60) as i64
    }
}

fn yes() -> bool {
    true
}
fn region() -> String {
    "us-east-1".into()
}
fn prefix() -> String {
    "fred-manager".into()
}
fn access_key() -> String {
    "FRED_CONTENT_ACCESS_KEY".into()
}
fn secret_key() -> String {
    "FRED_CONTENT_SECRET_KEY".into()
}
fn temp_dir() -> String {
    "/tmp/fred-manager-uploads".into()
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> ContentConfig {
        serde_json::from_value(
            serde_json::json!({"endpoint":"https://s3.example.test", "bucket":"originals"}),
        )
        .unwrap()
    }
    #[test]
    fn refuses_unbounded_or_unsafe_storage_configuration() {
        let good = config();
        good.validate().unwrap();
        for endpoint in [
            "http://s3.example.test",
            "https://user:secret@example.test",
            "https://example.test/?secret=x",
            "file:///tmp",
        ] {
            let mut bad = good.clone();
            bad.endpoint = endpoint.into();
            assert!(bad.validate().is_err());
        }
        let mut bad = good.clone();
        bad.limits.file_bytes = MAX_FILE_BYTES + 1;
        assert!(bad.validate().is_err());
        let mut bad = good.clone();
        bad.limits.temp_bytes = 1;
        assert!(bad.validate().is_err());
        let mut bad = good.clone();
        bad.limits.uploads = 0;
        assert!(bad.validate().is_err());
        let mut bad = good.clone();
        bad.cleanup_enabled = false;
        assert!(bad.validate().is_err());
        let mut bad = good;
        bad.prefix = "../other".into();
        assert!(bad.validate().is_err());
    }
}
