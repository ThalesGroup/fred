// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Configuration, on fred's model: a YAML file named by CONFIG_FILE (default
//! ./config/configuration.yaml) with the same section and field names as the Python
//! backends, and secrets only from the environment (FRED_POSTGRES_PASSWORD,
//! OPENFGA_API_TOKEN). FRED_STRICT_* / FRED_JWT_* stay environment toggles.

use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use sqlx::postgres::PgConnectOptions;

use crate::{
    auth::{Provider, SecuritySettings, UserClaims},
    logging::LogFormat,
};

#[derive(Debug, Clone, Deserialize)]
pub struct Configuration {
    pub app: AppConfig,
    pub security: SecurityConfig,
    pub storage: StorageConfig,
    pub scheduler: SchedulerConfig,
    #[serde(default)]
    pub policies: crate::lifecycle::policy::Policies,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AppConfig {
    /// Active terms version; null disables consent gating.
    #[serde(default, deserialize_with = "terms_version")]
    pub gcu_version: Option<String>,
    pub base_url: String,
    #[serde(default = "default_address")]
    pub address: String,
    pub port: u16,
    #[serde(default = "default_log_level")]
    pub log_level: String,
    /// `json` (one object per stdout line) or `text`, as the Python APIs' `app.log_format`.
    #[serde(default)]
    pub log_format: LogFormat,
    /// Root-bootstrap secret, read from this environment variable.
    #[serde(default)]
    pub bootstrap_token_env_var: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SecurityConfig {
    #[serde(default)]
    pub profile: Option<String>,
    #[serde(default)]
    pub m2m: Option<M2mConfig>,
    pub user: UserConfig,
    #[serde(default)]
    pub authorized_origins: Vec<String>,
    pub rebac: RebacConfig,
}

/// Issuer plus optional outbound directory credentials; legacy issuer-only configs remain valid.
#[derive(Debug, Clone, Deserialize)]
pub struct M2mConfig {
    pub realm_url: String,
    #[serde(default)]
    pub enabled: bool,
    pub client_id: Option<String>,
    pub secret_env_var: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct UserConfig {
    #[serde(default = "yes")]
    pub enabled: bool,
    pub realm_url: String,
    pub client_id: String,
    #[serde(default = "default_provider")]
    pub provider: String,
    #[serde(default)]
    pub audience: Option<String>,
    #[serde(default)]
    pub jwks_url: Option<String>,
    #[serde(default)]
    pub roles_claim: Option<Vec<String>>,
    #[serde(default)]
    pub claims: ClaimsConfig,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct ClaimsConfig {
    pub uid: Option<String>,
    pub username: Option<String>,
    pub email: Option<String>,
    pub given_name: Option<String>,
    pub family_name: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RebacConfig {
    pub api_url: String,
    /// Never fred's own store: syncing this model there would replace fred's.
    #[serde(default = "default_store")]
    pub store_name: String,
    #[serde(default = "yes")]
    pub create_store_if_needed: bool,
    #[serde(default = "yes")]
    pub sync_schema_on_init: bool,
    #[serde(default = "default_token_env")]
    pub token_env_var: String,
    #[serde(default = "default_timeout")]
    pub timeout_millisec: Option<u64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct StorageConfig {
    pub postgres: PostgresConfig,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PostgresConfig {
    pub host: String,
    #[serde(default = "default_pg_port")]
    pub port: u16,
    pub database: String,
    pub username: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SchedulerConfig {
    #[serde(default)]
    pub lifecycle: crate::lifecycle::policy::LifecycleConfig,
}

fn terms_version<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Option<String>, D::Error> {
    let version = Option::<String>::deserialize(d)?;
    if version.as_ref().is_some_and(|v| {
        v.is_empty() || v.len() > 128 || v.trim() != v || v.chars().any(char::is_control)
    }) {
        return Err(serde::de::Error::custom(
            "gcu_version must be null or a nonblank version of at most 128 bytes",
        ));
    }
    Ok(version)
}

fn yes() -> bool {
    true
}
fn default_log_level() -> String {
    "info".into()
}
fn default_address() -> String {
    "0.0.0.0".into()
}
fn default_provider() -> String {
    "keycloak".into()
}
fn default_store() -> String {
    "fred-manager".into()
}
fn default_token_env() -> String {
    "OPENFGA_API_TOKEN".into()
}
fn default_timeout() -> Option<u64> {
    Some(5000)
}
fn default_pg_port() -> u16 {
    5432
}

fn opt_env(name: &str) -> Option<String> {
    std::env::var(name).ok().filter(|v| !v.is_empty())
}

/// fred-core `coerce_bool`: known tokens only, anything else keeps the default.
fn flag(name: &str, default: bool) -> bool {
    match opt_env(name).map(|v| v.trim().to_lowercase()).as_deref() {
        Some("1" | "true" | "yes" | "on" | "y") => true,
        Some("0" | "false" | "no" | "off" | "n") => false,
        _ => default,
    }
}

fn number<T: std::str::FromStr>(name: &str, default: T) -> Result<T> {
    match opt_env(name) {
        Some(v) => v.parse().ok().with_context(|| format!("invalid {name}")),
        None => Ok(default),
    }
}

impl Configuration {
    pub fn load() -> Result<(String, Self)> {
        let path =
            std::env::var("CONFIG_FILE").unwrap_or_else(|_| "./config/configuration.yaml".into());
        let text = std::fs::read_to_string(&path).with_context(|| format!("cannot read {path}"))?;
        let config: Self =
            serde_yaml_ng::from_str(&text).with_context(|| format!("invalid {path}"))?;
        config.scheduler.lifecycle.validate()?;
        Ok((path, config))
    }

    pub fn listen_addr(&self) -> String {
        format!("{}:{}", self.app.address, self.app.port)
    }

    pub fn postgres(&self) -> Result<PgConnectOptions> {
        let pg = &self.storage.postgres;
        let password =
            opt_env("FRED_POSTGRES_PASSWORD").context("FRED_POSTGRES_PASSWORD is required")?;
        Ok(PgConnectOptions::new()
            .host(&pg.host)
            .port(pg.port)
            .database(&pg.database)
            .username(&pg.username)
            .password(&password))
    }

    pub fn fga_token(&self) -> Option<String> {
        opt_env(&self.security.rebac.token_env_var)
    }

    pub fn fga_timeout(&self) -> Option<Duration> {
        self.security
            .rebac
            .timeout_millisec
            .map(Duration::from_millis)
    }

    pub fn security(&self) -> Result<SecuritySettings> {
        let s = &self.security;
        let u = &s.user;
        let defaults = UserClaims::default();
        Ok(SecuritySettings {
            enabled: u.enabled,
            provider: match u.provider.as_str() {
                "keycloak" => Provider::Keycloak,
                "oidc" => Provider::Oidc,
                other => bail!("Unsupported identity provider: {other}"),
            },
            realm_url: u.realm_url.clone(),
            client_id: u.client_id.clone(),
            audience: u.audience.clone(),
            jwks_url: u.jwks_url.clone(),
            roles_claim: u.roles_claim.clone(),
            claims: UserClaims {
                uid: u.claims.uid.clone().unwrap_or(defaults.uid),
                username: u.claims.username.clone().unwrap_or(defaults.username),
                email: u.claims.email.clone().unwrap_or(defaults.email),
                given_name: u.claims.given_name.clone().unwrap_or(defaults.given_name),
                family_name: u.claims.family_name.clone().unwrap_or(defaults.family_name),
            },
            m2m_realm_url: s.m2m.as_ref().map(|m| m.realm_url.clone()),
            profile_c3: match s.profile.as_deref() {
                None => false,
                Some("c3") => true,
                Some(other) => bail!("Unsupported security profile: {other}"),
            },
            strict_issuer: flag("FRED_STRICT_ISSUER", false),
            strict_audience: flag("FRED_STRICT_AUDIENCE", false),
            clock_skew_seconds: number("FRED_JWT_CLOCK_SKEW", 0)?,
            max_token_lifetime_seconds: number("FRED_JWT_MAX_LIFETIME_SECONDS", 3600.0)?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Proves: I19
    #[test]
    fn active_terms_version_is_explicit_and_validated() {
        let shipped = include_str!("../config/configuration.yaml");
        for invalid in ["", " v1", "v1 ", "v1\n", &"x".repeat(129)] {
            let mut config: serde_json::Value = serde_yaml_ng::from_str(shipped).unwrap();
            config["app"]["gcu_version"] = invalid.into();
            assert!(serde_json::from_value::<Configuration>(config).is_err());
        }
        let mut config: serde_json::Value = serde_yaml_ng::from_str(shipped).unwrap();
        config["app"]["gcu_version"] = serde_json::Value::Null;
        assert!(
            serde_json::from_value::<Configuration>(config)
                .unwrap()
                .app
                .gcu_version
                .is_none()
        );
    }

    #[test]
    fn parses_the_shipped_configuration() {
        let text = include_str!("../config/configuration.yaml");
        let config: Configuration = serde_yaml_ng::from_str(text).unwrap();
        assert_eq!(config.security.rebac.store_name, "fred-manager");
        assert_eq!(config.app.base_url, "/fred-manager/v1");
        assert!(config.security().unwrap().profile_c3);
    }
}
