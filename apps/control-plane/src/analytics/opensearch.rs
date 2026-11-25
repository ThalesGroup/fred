// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! OpenSearch adapter for successful skill-load observations, not application authority.
use super::history::{ReadError, ReadScope, Reader, SkillLoads, SkillResult, ToolCount, TurnCount};
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
            "size": 0, "timeout": "4s", "track_total_hits": true,
            "query": {"bool": {"filter": [
                {"term": {"metric.name": "agent.skill_loaded_total"}},
                subject_filter(q.subject),
                calendar_filter(&q.excluded_dates),
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
        if q.attribution {
            for name in ["session_id", "finish_reason"] {
                validate_keyword(
                    &mapping[&self.config.index]["mappings"]["properties"]["dims"]["properties"]
                        [name],
                )?;
            }
        }
        let mut sources = vec![
            json!({"space":{"terms":{"field":"dims.space_id"}}}),
            json!({"agent":{"terms":{"field":"dims.agent_instance_id"}}}),
        ];
        if q.attribution {
            for (key, field) in [("user", "dims.user_id"), ("session", "dims.session_id")] {
                sources.push(json!({key:{"terms":{"field":field,"missing_bucket":true}}}));
            }
        }
        if let Some(bucket) = q.bucket {
            sources.push(json!({"start":{"date_histogram":{
                "field":"@timestamp", "calendar_interval":bucket, "time_zone":"UTC"
            }}}));
        }
        let mut aggregations = json!({"latest":{"top_hits":{"size":1,
            "sort":[{"@timestamp":"desc"},{"dims.agent_instance_name":"asc"}],
            "_source":{"includes":["@timestamp","dims.agent_instance_name"]}
        }}});
        if q.attribution {
            aggregations["failed"] = json!({"filter":{"term":{"dims.finish_reason":"error"}}});
            aggregations["known_outcome"] = json!({"filter":{"bool":{"filter":[{"exists":{"field":"dims.finish_reason"}}],"must_not":[{"term":{"dims.finish_reason":""}}]}}});
        }
        let response = self
            .json(
                reqwest::Method::POST,
                "_search?allow_partial_search_results=false",
                Some(json!({
                    "size":0, "timeout":"4s", "track_total_hits":true,
                    "query":{"bool":{"filter":[
                        {"term":{"metric.name":"agent.turn_completed"}},
                        subject_filter(q.subject),
                calendar_filter(&q.excluded_dates),
                        {"terms":{"dims.space_id":q.spaces}},
                        {"range":{"@timestamp":{"gte":q.since,"lt":q.until}}}
                    ]}},
                    "aggs":{"turns":{
                        "composite":{"size":MAX_GROUPS+1,"sources":sources},
                        "aggs":aggregations
                    }}
                })),
            )
            .await?;
        parse_turns(response, q.spaces, q.bucket.is_some(), q.attribution)
    }
    async fn read_tools(&self, q: ReadScope<'_>) -> Result<Vec<ToolCount>, ReadError> {
        if q.spaces.is_empty() {
            return Err(ReadError::Unavailable);
        }
        let mapping = self.json(reqwest::Method::GET, "_mapping", None).await?;
        validate_mapping(&mapping, &self.config.index, true)?;
        for name in ["tool_name", "status"] {
            validate_keyword(
                &mapping[&self.config.index]["mappings"]["properties"]["dims"]["properties"][name],
            )?;
        }
        let reply = self.json(reqwest::Method::POST,"_search?allow_partial_search_results=false",Some(json!({
            "size":0,"timeout":"4s","track_total_hits":true,
            "query":{"bool":{"filter":[
                {"term":{"metric.name":"agent.tool_latency_ms"}},
                subject_filter(q.subject),calendar_filter(&q.excluded_dates),
                {"terms":{"dims.space_id":q.spaces}},
                {"range":{"@timestamp":{"gte":q.since,"lt":q.until}}}
            ]}},
            "aggs":{"tools":{"composite":{"size":MAX_GROUPS+1,"sources":[
                {"tool":{"terms":{"field":"dims.tool_name","missing_bucket":true}}},
                {"agent":{"terms":{"field":"dims.agent_instance_id","missing_bucket":true}}},
                {"status":{"terms":{"field":"dims.status","missing_bucket":true}}}
            ]}}}
        }))).await?;
        parse_tools(reply)
    }
}

// A collective read deliberately has no person predicate. Its nonempty space list
// has already been resolved and authorized by Control Plane, never by the browser.
fn subject_filter(subject: Option<&str>) -> Value {
    match subject {
        Some(subject) => json!({"term":{"dims.user_id":subject}}),
        None => json!({"match_all":{}}),
    }
}

fn validate_keyword(field: &Value) -> Result<(), ReadError> {
    if field["type"] != "keyword"
        || field["index"] == false
        || field["doc_values"] == false
        || field.get("ignore_above").is_some()
        || field.get("normalizer").is_some()
    {
        return Err(ReadError::Unavailable);
    }
    Ok(())
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
    let mut seen = std::collections::BTreeSet::new();
    let mut observed = 0u64;
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
            observed = observed
                .checked_add(user)
                .and_then(|n| n.checked_add(agent))
                .ok_or(ReadError::TooLarge)?;
            let name = b["key"]["skill"].as_str().ok_or(ReadError::Unavailable)?;
            if !seen.insert(name) {
                return Err(ReadError::Unavailable);
            }
            Ok(SkillLoads {
                name: name.to_owned(),
                user,
                agent,
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    if response["hits"]["total"]["relation"] != "eq"
        || response["hits"]["total"]["value"].as_u64() != Some(observed)
    {
        return Err(ReadError::Unavailable);
    }
    rows.sort_by(|a, b| {
        (b.user + b.agent)
            .cmp(&(a.user + a.agent))
            .then_with(|| a.name.cmp(&b.name))
    });
    let truncated = rows.len() > limit;
    rows.truncate(limit);
    Ok(SkillResult { rows, truncated })
}

fn parse_turns(
    response: Value,
    spaces: &[uuid::Uuid],
    timed: bool,
    attribution: bool,
) -> Result<Vec<TurnCount>, ReadError> {
    validate_response(&response)?;
    let spaces: std::collections::BTreeSet<_> = spaces.iter().copied().collect();
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
            let start = if timed {
                Some(
                    b["key"]["start"]
                        .as_i64()
                        .and_then(chrono::DateTime::from_timestamp_millis)
                        .ok_or(ReadError::Unavailable)?,
                )
            } else {
                None
            };
            let identity = |key: &str| -> Result<Option<String>, ReadError> {
                if !attribution {
                    return Ok(None);
                }
                let value = b["key"].get(key).ok_or(ReadError::Unavailable)?;
                if value.is_null() {
                    return Ok(None);
                }
                value
                    .as_str()
                    .filter(|s| !s.is_empty() && s.len() <= 512)
                    .map(|s| Some(s.to_owned()))
                    .ok_or(ReadError::Unavailable)
            };
            let user_id = identity("user")?;
            let session_id = identity("session")?;
            if !spaces.contains(&space_id)
                || !seen.insert((
                    space_id,
                    agent_instance_id,
                    start,
                    user_id.clone(),
                    session_id.clone(),
                ))
            {
                return Err(ReadError::Unavailable);
            }
            let count = b["doc_count"]
                .as_u64()
                .filter(|n| *n > 0)
                .ok_or(ReadError::Unavailable)?;
            total = total.checked_add(count).ok_or(ReadError::TooLarge)?;
            let failed = if attribution {
                let known = b["known_outcome"]["doc_count"]
                    .as_u64()
                    .filter(|n| *n <= count)
                    .ok_or(ReadError::Unavailable)?;
                let failed = b["failed"]["doc_count"]
                    .as_u64()
                    .filter(|n| *n <= known)
                    .ok_or(ReadError::Unavailable)?;
                (known == count).then_some(failed)
            } else {
                None
            };
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
                start,
                user_id,
                session_id,
                failed,
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
    fn tools<'a>(
        &'a self,
        query: ReadScope<'a>,
    ) -> BoxFuture<'a, Result<Vec<ToolCount>, ReadError>> {
        Box::pin(self.read_tools(query))
    }
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

fn calendar_filter(excluded: &[chrono::NaiveDate]) -> Value {
    if excluded.is_empty() {
        return json!({"match_all":{}});
    }
    let ranges: Vec<_> = excluded
        .iter()
        .map(|d| {
            json!({"range":{"@timestamp":{
                "gte":format!("{d}T00:00:00Z"),
                "lt":format!("{}T00:00:00Z",*d+chrono::Duration::days(1))
            }}})
        })
        .collect();
    json!({"bool":{"must_not":ranges}})
}

fn parse_tools(reply: Value) -> Result<Vec<ToolCount>, ReadError> {
    validate_response(&reply)?;
    let buckets = reply["aggregations"]["tools"]["buckets"]
        .as_array()
        .ok_or(ReadError::Unavailable)?;
    if buckets.len() > MAX_GROUPS {
        return Err(ReadError::TooLarge);
    }
    let mut rows = std::collections::BTreeMap::<String, ToolCount>::new();
    let mut seen = std::collections::BTreeSet::new();
    let mut total = 0u64;
    for b in buckets {
        let name = b["key"]["tool"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 512)
            .ok_or(ReadError::Unavailable)?;
        let agent = b["key"]["agent"]
            .as_str()
            .and_then(|s| s.parse::<uuid::Uuid>().ok())
            .ok_or(ReadError::Unavailable)?;
        let status = b["key"].get("status").ok_or(ReadError::Unavailable)?;
        if !status.is_null() && !status.is_string() {
            return Err(ReadError::Unavailable);
        }
        if !seen.insert((name, agent, status.as_str())) {
            return Err(ReadError::Unavailable);
        }
        let count = b["doc_count"]
            .as_u64()
            .filter(|n| *n > 0)
            .ok_or(ReadError::Unavailable)?;
        total = total.checked_add(count).ok_or(ReadError::TooLarge)?;
        let row = rows.entry(name.into()).or_insert_with(|| ToolCount {
            name: name.into(),
            attempts: 0,
            outcomes: Some([0; 4]),
        });
        row.attempts = row.attempts.checked_add(count).ok_or(ReadError::TooLarge)?;
        let index = match status.as_str() {
            Some("ok") => Some(0),
            Some("error") => Some(1),
            Some("cancelled") => Some(2),
            Some("awaiting_human") => Some(3),
            _ => None,
        };
        match (row.outcomes.as_mut(), index) {
            (Some(o), Some(i)) => o[i] = o[i].checked_add(count).ok_or(ReadError::TooLarge)?,
            _ => row.outcomes = None,
        }
    }
    if reply["hits"]["total"]["relation"] != "eq"
        || reply["hits"]["total"]["value"].as_u64() != Some(total)
    {
        return Err(ReadError::Unavailable);
    }
    Ok(rows.into_values().collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tool_source_rejects_partial_or_unattributed_facts() {
        let mut reply = json!({"timed_out":false,"_shards":{"total":1,"successful":1,"failed":0},
        "hits":{"total":{"relation":"eq","value":2}},"aggregations":{"tools":{"buckets":[
            {"key":{"tool":"search","agent":uuid::Uuid::from_u128(1),"status":"ok"},"doc_count":1},
            {"key":{"tool":"search","agent":uuid::Uuid::from_u128(1),"status":"awaiting_human"},"doc_count":1}
        ]}}});
        let rows = parse_tools(reply.clone()).unwrap();
        assert_eq!(rows[0].outcomes, Some([1, 0, 0, 1]));
        reply["aggregations"]["tools"]["buckets"][1]["key"]["status"] = Value::Null;
        assert!(parse_tools(reply.clone()).unwrap()[0].outcomes.is_none());
        reply["aggregations"]["tools"]["buckets"][1]["key"]["agent"] = Value::Null;
        assert!(parse_tools(reply).is_err());
        let filter = calendar_filter(&["2026-01-01".parse().unwrap()]);
        assert_eq!(
            filter["bool"]["must_not"][0]["range"]["@timestamp"]["lt"],
            "2026-01-02T00:00:00Z"
        );
    }

    #[test]
    fn collective_attribution_is_exact_and_missing_identity_is_not_zero() {
        let space = uuid::Uuid::from_u128(1);
        let agent = uuid::Uuid::from_u128(2);
        let bucket = json!({"key":{"space":space,"agent":agent,"user":null,"session":"s","start":1767225600000_i64},
            "doc_count":2,"failed":{"doc_count":1},"known_outcome":{"doc_count":2},
            "latest":{"hits":{"hits":[{"_source":{"@timestamp":"2026-01-01T10:00:00Z","dims":{"agent_instance_name":"A"}}}]}}});
        let reply = json!({"timed_out":false,"_shards":{"total":1,"successful":1,"failed":0},
            "hits":{"total":{"relation":"eq","value":2}},"aggregations":{"turns":{"buckets":[bucket.clone()]}}});
        let rows = parse_turns(reply.clone(), &[space], true, true).unwrap();
        assert_eq!(rows[0].user_id, None);
        assert_eq!(rows[0].failed, Some(1));
        assert!(rows[0].start.is_some());
        assert_eq!(subject_filter(None), json!({"match_all":{}}));
        assert!(parse_turns(reply.clone(), &[agent], true, true).is_err());
        let mut partial = reply.clone();
        partial["hits"]["total"]["value"] = json!(3);
        assert!(parse_turns(partial, &[space], true, true).is_err());
        let mut unknown = reply.clone();
        unknown["aggregations"]["turns"]["buckets"][0]["known_outcome"]["doc_count"] = json!(1);
        assert_eq!(
            parse_turns(unknown, &[space], true, true).unwrap()[0].failed,
            None
        );
        let mut duplicate = reply;
        duplicate["aggregations"]["turns"]["buckets"]
            .as_array_mut()
            .unwrap()
            .push(bucket);
        assert!(parse_turns(duplicate, &[space], true, true).is_err());
    }
}
