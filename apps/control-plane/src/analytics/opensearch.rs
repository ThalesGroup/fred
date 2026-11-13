// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! OpenSearch adapter for successful skill-load observations, not application authority.
use super::history::{ReadError, ReadScope, Reader, SkillLoads, SkillResult, TurnCount};
use futures::future::BoxFuture;
use reqwest::{Client, Url};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{sync::Arc, time::Duration};
use utoipa::ToSchema;

const MAX_GROUPS: usize = 10_000;
const MAX_BYTES: usize = 8 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub url: String,
    /// A single concrete KPI index, not a pattern or alias spanning indexes.
    pub index: String,
    pub username: Option<String>,
    pub password_env_var: Option<String>,
}

impl Config {
    pub fn validate(&self) -> anyhow::Result<()> {
        let url = Url::parse(&self.url)?;
        anyhow::ensure!(
            matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
                && url.path() == "/",
            "invalid historical source URL"
        );
        anyhow::ensure!(
            !self.index.is_empty()
                && self
                    .index
                    .bytes()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"-_".contains(&c))
                && !self.index.starts_with(['-', '_']),
            "expected a concrete historical index"
        );
        anyhow::ensure!(
            self.username.is_some() == self.password_env_var.is_some(),
            "historical credentials require username and password_env_var"
        );
        Ok(())
    }
}

pub struct OpenSearch {
    client: Client,
    config: Config,
    password: Option<String>,
}

impl OpenSearch {
    pub fn configured(config: &Config) -> anyhow::Result<Arc<dyn Reader>> {
        config.validate()?;
        let password = config
            .password_env_var
            .as_ref()
            .map(|name| {
                crate::config::opt_env(name).ok_or_else(|| {
                    anyhow::anyhow!("missing historical credential environment variable")
                })
            })
            .transpose()?;
        // Shared pooled client for the lifetime of the adapter; TLS verification stays enabled.
        let client = Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .connect_timeout(Duration::from_secs(2))
            .timeout(Duration::from_secs(5))
            .build()?;
        Ok(Arc::new(Self {
            client,
            config: config.clone(),
            password,
        }))
    }

    async fn json(
        &self,
        method: reqwest::Method,
        suffix: &str,
        body: Option<Value>,
    ) -> Result<Value, ReadError> {
        let url = format!(
            "{}/{}/{}",
            self.config.url.trim_end_matches('/'),
            self.config.index,
            suffix
        );
        let mut request = self.client.request(method, url);
        if let Some(username) = &self.config.username {
            request = request.basic_auth(username, self.password.as_deref());
        }
        if let Some(body) = body {
            request = request.json(&body);
        }
        let mut response = request
            .send()
            .await
            .map_err(|_| ReadError::Unavailable)?
            .error_for_status()
            .map_err(|_| ReadError::Unavailable)?;
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| ReadError::Unavailable)? {
            if bytes.len() + chunk.len() > MAX_BYTES {
                return Err(ReadError::TooLarge);
            }
            bytes.extend_from_slice(&chunk);
        }
        serde_json::from_slice(&bytes).map_err(|_| ReadError::Unavailable)
    }

    async fn read(&self, q: ReadScope<'_>) -> Result<SkillResult, ReadError> {
        if q.spaces.is_empty() {
            return Err(ReadError::Unavailable);
        }
        // Check the concrete mapping, not _source: dynamic:false can retain unindexed fields.
        let mapping = self.json(reqwest::Method::GET, "_mapping", None).await?;
        validate_mapping(&mapping, &self.config.index, false)?;
        let response = self.json(reqwest::Method::POST, "_search?allow_partial_search_results=false", Some(json!({
            "size": 0, "timeout": "4s", "track_total_hits": false,
            "query": {"bool": {"filter": [
                {"term": {"metric.name": "agent.skill_loaded_total"}},
                {"term": {"dims.user_id": q.subject}},
                {"terms": {"dims.space_id": q.spaces}},
                {"terms": {"dims.skill_origin": ["user", "agent"]}},
                {"range": {"@timestamp": {"gte": q.since, "lt": q.until}}}
            ]}},
            "aggs": {"skills": {
                // Composite collects every shard's counts exactly. A bounded full set allows
                // a real global top-N; terms-by-count would silently lose sub-aggregation counts.
                "composite": {"size": MAX_GROUPS + 1, "sources": [{"skill": {"terms": {"field": "dims.skill_name"}}}]},
                "aggs": {"origins": {"filters": {"filters": {
                    "user": {"term": {"dims.skill_origin": "user"}},
                    "agent": {"term": {"dims.skill_origin": "agent"}}
                }}}}
            }}
        }))).await?;
        parse(response, q.limit)
    }
    async fn read_turns(&self, q: ReadScope<'_>) -> Result<Vec<TurnCount>, ReadError> {
        if q.spaces.is_empty() {
            return Err(ReadError::Unavailable);
        }
        let mapping = self.json(reqwest::Method::GET, "_mapping", None).await?;
        validate_mapping(&mapping, &self.config.index, true)?;
        let response = self
            .json(
                reqwest::Method::POST,
                "_search?allow_partial_search_results=false",
                Some(json!({
                    "size":0, "timeout":"4s", "track_total_hits":true,
                    "query":{"bool":{"filter":[
                        {"term":{"metric.name":"agent.turn_completed"}},
                        {"term":{"dims.user_id":q.subject}},
                        {"terms":{"dims.space_id":q.spaces}},
                        {"range":{"@timestamp":{"gte":q.since,"lt":q.until}}}
                    ]}},
                    "aggs":{"turns":{
                        "composite":{"size":MAX_GROUPS+1,"sources":[
                            {"space":{"terms":{"field":"dims.space_id"}}},
                            {"agent":{"terms":{"field":"dims.agent_instance_id"}}}
                        ]},
                        "aggs":{"latest":{"top_hits":{"size":1,
                            "sort":[{"@timestamp":"desc"},{"dims.agent_instance_name":"asc"}],
                            "_source":{"includes":["@timestamp","dims.agent_instance_name"]}
                        }}}
                    }}
                })),
            )
            .await?;
        parse_turns(response, q.spaces)
    }
}

fn validate_mapping(mapping: &Value, index: &str, turns: bool) -> Result<(), ReadError> {
    if mapping.as_object().map(|o| o.len()) != Some(1) {
        return Err(ReadError::Unavailable);
    }
    let properties = &mapping[index]["mappings"]["properties"];
    if properties["dims"]["enabled"] == false || properties["metric"]["enabled"] == false {
        return Err(ReadError::Unavailable);
    }
    let specific = if turns {
        [
            ("/dims/properties/agent_instance_id/type", "keyword"),
            ("/dims/properties/agent_instance_name/type", "keyword"),
        ]
    } else {
        [
            ("/dims/properties/skill_name/type", "keyword"),
            ("/dims/properties/skill_origin/type", "keyword"),
        ]
    };
    for (path, kind) in [
        ("/@timestamp/type", "date"),
        ("/metric/properties/name/type", "keyword"),
        ("/dims/properties/user_id/type", "keyword"),
        ("/dims/properties/space_id/type", "keyword"),
    ]
    .into_iter()
    .chain(specific)
    {
        if properties.pointer(path).and_then(Value::as_str) != Some(kind) {
            return Err(ReadError::Unavailable);
        }
        let parent = properties
            .pointer(path.trim_end_matches("/type"))
            .ok_or(ReadError::Unavailable)?;
        if parent["index"] == false
            || parent["doc_values"] == false
            || parent.get("ignore_above").is_some()
            || parent.get("normalizer").is_some()
        {
            return Err(ReadError::Unavailable);
        }
    }
    Ok(())
}

fn validate_response(response: &Value) -> Result<(), ReadError> {
    if response["timed_out"] != false
        || response["_shards"]["failed"].as_u64() != Some(0)
        || response["_shards"]["total"].as_u64().is_none_or(|n| n == 0)
        || response["_shards"]["successful"] != response["_shards"]["total"]
    {
        return Err(ReadError::Unavailable);
    }
    Ok(())
}

fn parse(response: Value, limit: usize) -> Result<SkillResult, ReadError> {
    validate_response(&response)?;
    let buckets = response["aggregations"]["skills"]["buckets"]
        .as_array()
        .ok_or(ReadError::Unavailable)?;
    if buckets.len() > MAX_GROUPS {
        return Err(ReadError::TooLarge);
    }
    let mut rows = buckets
        .iter()
        .map(|b| {
            let user = b["origins"]["buckets"]["user"]["doc_count"]
                .as_u64()
                .ok_or(ReadError::Unavailable)?;
            let agent = b["origins"]["buckets"]["agent"]["doc_count"]
                .as_u64()
                .ok_or(ReadError::Unavailable)?;
            if Some(user.checked_add(agent).ok_or(ReadError::Unavailable)?)
                != b["doc_count"].as_u64()
            {
                return Err(ReadError::Unavailable);
            }
            Ok(SkillLoads {
                name: b["key"]["skill"]
                    .as_str()
                    .ok_or(ReadError::Unavailable)?
                    .to_owned(),
                user,
                agent,
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    rows.sort_by(|a, b| {
        (b.user + b.agent)
            .cmp(&(a.user + a.agent))
            .then_with(|| a.name.cmp(&b.name))
    });
    let truncated = rows.len() > limit;
    rows.truncate(limit);
    Ok(SkillResult { rows, truncated })
}

fn parse_turns(response: Value, spaces: &[uuid::Uuid]) -> Result<Vec<TurnCount>, ReadError> {
    validate_response(&response)?;
    let buckets = response["aggregations"]["turns"]["buckets"]
        .as_array()
        .ok_or(ReadError::Unavailable)?;
    if buckets.len() > MAX_GROUPS {
        return Err(ReadError::TooLarge);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut total = 0u64;
    let rows = buckets
        .iter()
        .map(|b| {
            let space_id = b["key"]["space"]
                .as_str()
                .and_then(|s| s.parse().ok())
                .ok_or(ReadError::Unavailable)?;
            let agent_instance_id = b["key"]["agent"]
                .as_str()
                .and_then(|s| s.parse().ok())
                .ok_or(ReadError::Unavailable)?;
            if !spaces.contains(&space_id) || !seen.insert((space_id, agent_instance_id)) {
                return Err(ReadError::Unavailable);
            }
            let count = b["doc_count"]
                .as_u64()
                .filter(|n| *n > 0)
                .ok_or(ReadError::Unavailable)?;
            total = total.checked_add(count).ok_or(ReadError::TooLarge)?;
            let source = &b["latest"]["hits"]["hits"][0]["_source"];
            let latest = source["@timestamp"]
                .as_str()
                .and_then(|s| s.parse().ok())
                .ok_or(ReadError::Unavailable)?;
            let display_name = source["dims"]["agent_instance_name"]
                .as_str()
                .map(str::to_owned);
            if display_name
                .as_ref()
                .is_some_and(|s| s.chars().count() > 255)
            {
                return Err(ReadError::Unavailable);
            }
            Ok(TurnCount {
                space_id,
                agent_instance_id,
                count,
                latest,
                display_name,
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    // Missing identities and incomplete aggregations must not masquerade as exact zero/counts.
    if response["hits"]["total"]["relation"] != "eq"
        || response["hits"]["total"]["value"].as_u64() != Some(total)
    {
        return Err(ReadError::Unavailable);
    }
    Ok(rows)
}

impl Reader for OpenSearch {
    fn completed_turns<'a>(
        &'a self,
        query: ReadScope<'a>,
    ) -> BoxFuture<'a, Result<Vec<TurnCount>, ReadError>> {
        Box::pin(self.read_turns(query))
    }

    fn skill_loads<'a>(
        &'a self,
        query: ReadScope<'a>,
    ) -> BoxFuture<'a, Result<SkillResult, ReadError>> {
        Box::pin(self.read(query))
    }
}
