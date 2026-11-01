// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{env, net::SocketAddr};

use anyhow::{Context, Result, bail};
use fred_rust_sdk::security::authentication::{
    DirectoryDelegation, Provider, SecuritySettings, UserClaims,
};

pub struct Config {
    pub bind: SocketAddr,
    pub namespace: Option<String>,
    pub database_url: String,
    pub security: SecuritySettings,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let required = |name: &str| -> Result<String> {
            let value = env::var(name).with_context(|| format!("{name} is required"))?;
            anyhow::ensure!(!value.trim().is_empty(), "{name} must not be empty");
            Ok(value)
        };
        let provider = match env::var("OIDC_PROVIDER").as_deref().unwrap_or("keycloak") {
            "keycloak" => Provider::Keycloak,
            "oidc" => Provider::Oidc,
            _ => bail!("OIDC_PROVIDER must be keycloak or oidc"),
        };
        Ok(Self {
            namespace: env::var("MONITOR_NAMESPACE").ok().filter(|s| !s.is_empty()),
            bind: env::var("MONITOR_BIND")
                .unwrap_or_else(|_| "127.0.0.1:8223".into())
                .parse()
                .context("invalid MONITOR_BIND socket address")?,
            database_url: required("DATABASE_URL")?,
            security: SecuritySettings {
                enabled: true,
                provider,
                realm_url: required("OIDC_ISSUER")?,
                client_id: required("OIDC_CLIENT_ID")?,
                audience: Some(required("OIDC_AUDIENCE")?),
                jwks_url: env::var("OIDC_JWKS_URL").ok(),
                claims: UserClaims::default(),
                roles_claim: None,
                m2m_realm_url: None,
                directory_delegation: DirectoryDelegation::default(),
                profile_c3: true,
                clock_skew_seconds: 0,
                max_token_lifetime_seconds: 3600.0,
            },
        })
    }
}
