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
//! OPENFGA_API_TOKEN). FRED_JWT_* stay environment settings.

use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use sqlx::postgres::PgConnectOptions;
use utoipa::ToSchema;

use crate::{
    auth::{Provider, SecuritySettings, UserClaims},
    logging::LogFormat,
};

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Configuration {
    pub app: AppConfig,
    pub security: SecurityConfig,
    pub storage: StorageConfig,
    pub scheduler: SchedulerConfig,
    #[serde(default)]
    pub platform: crate::agents::PlatformConfig,
    #[serde(default)]
    pub policies: crate::lifecycle::policy::Policies,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
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

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SecurityConfig {
    #[serde(default)]
    pub profile: Option<String>,
    #[serde(default)]
    pub m2m: Option<M2mConfig>,
    pub user: UserConfig,
    #[serde(default)]
    pub user_directory: crate::users::DirectoryKind,
    #[serde(default)]
    pub delegation: crate::users::DirectoryDelegation,
    #[serde(default)]
    pub authorized_origins: Vec<String>,
    pub rebac: RebacConfig,
}

/// Issuer plus outbound directory credentials, used only when `enabled`.
#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct M2mConfig {
    pub realm_url: String,
    pub enabled: bool,
    pub client_id: Option<String>,
    pub secret_env_var: Option<String>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
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

#[derive(Debug, Clone, Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ClaimsConfig {
    pub uid: Option<String>,
    pub username: Option<String>,
    pub email: Option<String>,
    pub given_name: Option<String>,
    pub family_name: Option<String>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
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

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StorageConfig {
    pub postgres: PostgresConfig,
    pub content: Option<crate::documents::config::ContentConfig>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PostgresConfig {
    pub host: String,
    #[serde(default = "default_pg_port")]
    pub port: u16,
    pub database: String,
    pub username: String,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SchedulerConfig {
    #[serde(default)]
    pub lifecycle: crate::lifecycle::policy::LifecycleConfig,
    #[serde(default)]
    pub processing: Option<crate::processing::config::ProcessingConfig>,
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

pub(crate) fn yes() -> bool {
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
    "control-plane".into()
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
        config.validate()?;
        Ok((path, config))
    }

    pub fn validate(&self) -> Result<()> {
        self.platform.validate()?;
        self.scheduler.lifecycle.validate()?;
        if let Some(content) = &self.storage.content {
            content.validate()?;
        }
        if let Some(processing) = &self.scheduler.processing {
            processing.validate(
                self.storage
                    .content
                    .as_ref()
                    .context("processing requires original storage")?,
            )?;
        }
        Ok(())
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
        if u.provider == "oidc" && s.user_directory != crate::users::DirectoryKind::Local {
            bail!("security.user_directory must be local when security.user.provider=oidc");
        }
        let defaults = UserClaims::default();
        Ok(SecuritySettings {
            directory_delegation: s.delegation.validated()?,
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
            clock_skew_seconds: number("FRED_JWT_CLOCK_SKEW", 0)?,
            max_token_lifetime_seconds: number("FRED_JWT_MAX_LIFETIME_SECONDS", 3600.0)?,
        })
    }
}

/// Generate the chart's configuration contract without loading runtime dependencies.
pub fn schema() -> serde_json::Value {
    use utoipa::OpenApi;
    #[derive(OpenApi)]
    #[openapi(components(schemas(Configuration)))]
    struct ConfigApi;
    let mut schema = serde_json::json!({
        "$schema": "https://json-schema.org/draft-07/schema#",
        "$ref": "#/$defs/Configuration",
        "$defs": ConfigApi::openapi().components.unwrap().schemas,
    });
    fn references(value: &mut serde_json::Value) {
        match value {
            serde_json::Value::Object(map) => {
                if let Some(serde_json::Value::String(reference)) = map.get_mut("$ref") {
                    *reference = reference.replace("#/components/schemas/", "#/$defs/");
                }
                for child in map.values_mut() {
                    references(child);
                }
            }
            serde_json::Value::Array(values) => values.iter_mut().for_each(references),
            _ => {}
        }
    }
    references(&mut schema);
    schema
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

    /// The chart's control-plane configuration, optionally overlaid like Helm values.
    fn chart(overlay: Option<&str>) -> serde_json::Value {
        fn section(text: &str) -> serde_json::Value {
            let values: serde_json::Value = serde_yaml_ng::from_str(text).unwrap();
            values["applications"]["control-plane-backend"]["configuration"].clone()
        }
        fn merge(base: &mut serde_json::Value, overlay: serde_json::Value) {
            match (base, overlay) {
                // An overlay without this section leaves the chart's own.
                (_, serde_json::Value::Null) => {}
                (serde_json::Value::Object(base), serde_json::Value::Object(overlay)) => {
                    for (key, value) in overlay {
                        merge(base.entry(key).or_insert(serde_json::Value::Null), value);
                    }
                }
                (base, overlay) => *base = overlay,
            }
        }
        let mut config = section(include_str!("../../../deploy/charts/fred/values.yaml"));
        if let Some(overlay) = overlay {
            merge(&mut config, section(overlay));
        }
        config
    }

    #[test]
    fn every_shipped_configuration_has_only_known_keys() {
        let shipped =
            serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
        let rendered = [
            ("shipped", shipped),
            ("chart", chart(None)),
            (
                "entra",
                chart(Some(include_str!(
                    "../../../deploy/charts/fred/values-entra.example.yaml"
                ))),
            ),
            (
                "gcp",
                chart(Some(include_str!(
                    "../../../deploy/charts/fred/values-gcp.yaml"
                ))),
            ),
            (
                "storage",
                chart(Some(include_str!(
                    "../../../deploy/charts/fred/examples/document-storage.yaml"
                ))),
            ),
            (
                "processing",
                chart(Some(include_str!(
                    "../../../deploy/charts/fred/examples/document-processing.yaml"
                ))),
            ),
        ];
        for (name, config) in rendered {
            if let Err(error) = serde_json::from_value::<Configuration>(config) {
                panic!("{name}: {error}");
            }
        }
    }

    #[test]
    fn an_unknown_key_at_any_level_is_refused_by_name() {
        let shipped: serde_json::Value =
            serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
        let mut processing = shipped.clone();
        processing["storage"]["content"] =
            serde_json::json!({"endpoint":"http://localhost:9000","bucket":"originals"});
        for path in [
            "",
            "/app",
            "/security",
            "/security/m2m",
            "/security/user",
            "/security/user/claims",
            "/security/delegation",
            "/security/rebac",
            "/storage",
            "/storage/postgres",
            "/storage/content",
            "/storage/content/limits",
            "/scheduler",
            "/scheduler/lifecycle",
            "/scheduler/lifecycle/temporal",
            "/policies",
        ] {
            let mut config = processing.clone();
            let mut node = &mut config;
            for key in path.split('/').filter(|k| !k.is_empty()) {
                node = node
                    .as_object_mut()
                    .unwrap()
                    .entry(key)
                    .or_insert_with(|| serde_json::json!({}));
            }
            node["misspelt_key"] = true.into();
            let error = serde_json::from_value::<Configuration>(config).unwrap_err();
            assert!(
                error.to_string().contains("misspelt_key"),
                "{path}: {error}"
            );
        }
    }

    #[test]
    fn parses_the_shipped_configuration() {
        let text = include_str!("../config/configuration.yaml");
        let config: Configuration = serde_yaml_ng::from_str(text).unwrap();
        assert_eq!(config.security.rebac.store_name, "control-plane");
        assert_eq!(config.app.base_url, "/control-plane/v1");
        assert!(config.security().unwrap().profile_c3);
    }
}
