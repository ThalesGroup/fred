// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One server-bound KF search. No tool argument can choose identity or corpus scope.

use std::{sync::LazyLock, time::Duration};

use fred_rust_agent::{
    search::{SearchHit, TOP_K},
    turn::InferenceError,
};
use reqwest::{Client, Url};
use uuid::Uuid;

use crate::keycloak::Directory;

static HTTP: LazyLock<Result<Client, reqwest::Error>> = LazyLock::new(|| {
    Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .build()
});

pub(crate) fn endpoint(base: &str) -> Result<Url, InferenceError> {
    let mut url = Url::parse(base).map_err(|_| InferenceError::Search)?;
    if !matches!(url.scheme(), "http" | "https")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err(InferenceError::Search);
    }
    url.set_path(&format!(
        "{}/documents/search",
        url.path().trim_end_matches('/')
    ));
    Ok(url)
}

pub(super) struct Search {
    url: Url,
    directory: Directory,
    context: String,
}

impl Search {
    pub(super) fn new(
        base: &str,
        directory: Option<Directory>,
        person: &str,
        agent: Uuid,
        space: Uuid,
    ) -> Result<Self, InferenceError> {
        let mut url = endpoint(base)?;
        url.query_pairs_mut()
            .append_pair("person", person)
            .append_pair("run", &Uuid::new_v4().to_string())
            .append_pair("agent", &agent.to_string());
        Ok(Self {
            url,
            directory: directory.ok_or(InferenceError::Search)?,
            // No selection clauses means the full authorized corpus. Attachments
            // remain excluded, independently of the session's published uploads.
            context: serde_json::json!({
                "space_id":space,
                "document_scope":{"selections":[]}, "attachment_ids":[]
            })
            .to_string(),
        })
    }

    pub(super) async fn run(self, query: String) -> Result<Vec<SearchHit>, InferenceError> {
        tokio::time::timeout(Duration::from_secs(30), self.fetch(query))
            .await
            .map_err(|_| InferenceError::Search)?
    }

    async fn fetch(self, query: String) -> Result<Vec<SearchHit>, InferenceError> {
        let client = HTTP.as_ref().map_err(|_| InferenceError::Search)?;
        let token = self
            .directory
            .access_token()
            .await
            .map_err(|_| InferenceError::Search)?;
        let mut response = client
            .post(self.url)
            .bearer_auth(token)
            .header("x-fred-document-context", self.context)
            .json(&serde_json::json!({"question":query,"top_k":TOP_K}))
            .send()
            .await
            .map_err(|_| InferenceError::Search)?;
        if !response.status().is_success() {
            return Err(InferenceError::Search);
        }
        // Everything relayed to the model and the browser comes from this bounded body.
        let mut body = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| InferenceError::Search)? {
            if body.len() + chunk.len() > 512 * 1024 {
                return Err(InferenceError::Search);
            }
            body.extend_from_slice(&chunk);
        }
        serde_json::from_slice(&body).map_err(|_| InferenceError::Search)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_endpoint_stays_under_the_configured_base() {
        assert_eq!(
            endpoint("https://kf.example/knowledge-flow/v2/")
                .unwrap()
                .as_str(),
            "https://kf.example/knowledge-flow/v2/documents/search"
        );
        for base in [
            "file:///tmp",
            "https://user:secret@kf.example",
            "https://kf.example?person=other",
            "https://kf.example#fragment",
        ] {
            assert!(endpoint(base).is_err());
        }
    }
}
