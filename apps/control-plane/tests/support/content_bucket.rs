// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use aws_sdk_s3::{
    Client,
    config::{BehaviorVersion, Credentials, Region},
};
use control_plane::documents::{config::ContentConfig, object_store::ObjectStore};
use std::{process::Command, time::Duration};
use uuid::Uuid;

pub struct Bucket {
    name: String,
    _config: tempfile::TempDir,
    pub config: ContentConfig,
    pub client: Client,
    pub store: ObjectStore,
}

impl Drop for Bucket {
    fn drop(&mut self) {
        let _ = Command::new("docker")
            .args(["rm", "-f", &self.name])
            .output();
    }
}

impl Bucket {
    pub async fn start() -> Self {
        let name = format!("fred-document-s3-{}", Uuid::new_v4().simple());
        let directory = tempfile::tempdir().unwrap();
        std::fs::write(directory.path().join("s3.json"), r#"{"identities":[{"name":"fixture","credentials":[{"accessKey":"fixture-access","secretKey":"fixture-secret"}],"actions":["Admin","Read","Write","List","Tagging"]}]}"#).unwrap();
        let volume = format!("{}:/fixture:ro", directory.path().display());
        let output = Command::new("docker")
            .args([
                "run",
                "-d",
                "--name",
                &name,
                "-p",
                "127.0.0.1::8333",
                // Keep disposable data independent of the host disk's free-space
                // threshold, with a fixed memory limit per fixture.
                "--tmpfs",
                "/tmp:rw,size=256m",
                "-v",
                &volume,
                "chrislusf/seaweedfs:4.29",
                "server",
                "-s3",
                "-s3.config=/fixture/s3.json",
                "-dir=/tmp",
                // Default growth allocates seven volumes per collection. Keep
                // room for both filer/system writes and the originals bucket;
                // a one-volume fixture fails once the system flushes its logs.
                "-volume.max=16",
            ])
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let port = Command::new("docker")
            .args(["port", &name, "8333/tcp"])
            .output()
            .unwrap();
        let endpoint = format!("http://{}", String::from_utf8(port.stdout).unwrap().trim());
        let config: ContentConfig = serde_json::from_value(
            serde_json::json!({"endpoint":endpoint,"bucket":"originals","allow_insecure":true}),
        )
        .unwrap();
        let client = Client::from_conf(
            aws_sdk_s3::Config::builder()
                .behavior_version(BehaviorVersion::latest())
                .region(Region::new("us-east-1"))
                .endpoint_url(&config.endpoint)
                .force_path_style(true)
                .credentials_provider(Credentials::new(
                    "fixture-access",
                    "fixture-secret",
                    None,
                    None,
                    "fixture",
                ))
                .retry_config(aws_sdk_s3::config::retry::RetryConfig::disabled())
                .timeout_config(
                    aws_sdk_s3::config::timeout::TimeoutConfig::builder()
                        .operation_timeout(Duration::from_secs(2))
                        .build(),
                )
                .build(),
        );
        let store =
            ObjectStore::new(&config, "fixture-access".into(), "fixture-secret".into()).unwrap();
        let fixture = Self {
            name,
            _config: directory,
            config,
            client,
            store,
        };
        for _ in 0..60 {
            if fixture
                .client
                .create_bucket()
                .bucket("originals")
                .send()
                .await
                .is_ok()
            {
                return fixture;
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
        panic!("disposable SeaweedFS did not become ready");
    }
}
