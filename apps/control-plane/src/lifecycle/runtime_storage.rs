// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Runtime-owned erasure, using the existing configured workload and private destination.
use crate::{agents::RuntimeCatalogSource, keycloak::Directory};
use anyhow::{Result, ensure};
use reqwest::{Client, StatusCode, Url};
use serde::Deserialize;
use std::{sync::LazyLock, time::Duration};
use uuid::Uuid;

static HTTP: LazyLock<Result<Client, reqwest::Error>> = LazyLock::new(|| {
    Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .build()
});

#[derive(Clone, Default)]
pub struct RuntimeStorage {
    pub sources: Vec<RuntimeCatalogSource>,
    pub directory: Option<Directory>,
}

pub enum Purge {
    Ready,
    Unavailable,
    WritesPending,
}

impl RuntimeStorage {
    /// Only verified runtime closure permits the final SQL cascade.
    pub async fn purge(&self, runtime: &str, session: Uuid) -> Result<Purge> {
        let Some(source) = self
            .sources
            .iter()
            .find(|s| s.enabled && s.runtime_id == runtime)
        else {
            return Ok(Purge::Unavailable);
        };
        let Some(directory) = &self.directory else {
            return Ok(Purge::Unavailable);
        };
        tokio::time::timeout(Duration::from_secs(25), async {
            let client = HTTP
                .as_ref()
                .map_err(|_| anyhow::anyhow!("runtime purge client unavailable"))?;
            let mut url = Url::parse(&source.base_url)?;
            ensure!(
                matches!(url.scheme(), "http" | "https")
                    && url.host_str().is_some()
                    && url.username().is_empty()
                    && url.password().is_none()
                    && url.query().is_none()
                    && url.fragment().is_none(),
                "invalid runtime purge destination"
            );
            url.set_path(&format!(
                "{}/agents/sessions/{session}",
                url.path().trim_end_matches('/')
            ));
            let token = directory.access_token().await?;
            let mut response = client.delete(url).bearer_auth(token).send().await?;
            let status = response.status();
            // A former runtime returned success after deleting history alone. Only
            // the explicit durable-purge result allows metadata removal.
            let mut body = Vec::new();
            while let Some(chunk) = response.chunk().await? {
                ensure!(
                    body.len() + chunk.len() <= 1024,
                    "invalid runtime purge response"
                );
                body.extend_from_slice(&chunk);
            }
            if status == StatusCode::SERVICE_UNAVAILABLE {
                #[derive(Deserialize)]
                struct Blocked {
                    detail: String,
                }
                if serde_json::from_slice::<Blocked>(&body)
                    .is_ok_and(|b| b.detail == "session_writes_pending")
                {
                    return Ok(Purge::WritesPending);
                }
            }
            ensure!(status == StatusCode::OK, "runtime purge refused");
            #[derive(Deserialize)]
            struct Purged {
                purged: bool,
                sql_cascade: bool,
            }
            ensure!(
                {
                    let result = serde_json::from_slice::<Purged>(&body)?;
                    result.purged && result.sql_cascade
                },
                "runtime purge incomplete"
            );
            Ok(Purge::Ready)
        })
        .await
        .map_err(|_| anyhow::anyhow!("runtime purge timed out"))?
    }
}
