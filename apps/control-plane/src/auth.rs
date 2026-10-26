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

//! Bearer authentication for UI callers, ported from fred-core `security/oidc.py`
//! (`decode_jwt`, `get_current_user_without_gcu`) and fred-pod `oidc_endpoints.py`.
//! Same configuration meaning, same claims mapping, same 401 details and headers.

use std::{
    collections::HashMap,
    fmt,
    sync::Arc,
    time::{Duration, Instant},
};

use anyhow::{Context, Result, bail};
use axum::{
    Json,
    extract::FromRequestParts,
    http::{StatusCode, header, request::Parts},
    response::{IntoResponse, Response},
};
use jsonwebtoken::{
    Algorithm, DecodingKey, Validation,
    errors::ErrorKind,
    jwk::{JwkSet, PublicKeyUse},
};
use serde_json::{Map, Value, json};
use tokio::sync::RwLock;
use uuid::Uuid;

// PyJWKClient defaults: the key set lives five minutes, and an unknown kid forces at
// most one refetch every thirty seconds.
const JWKS_LIFESPAN: Duration = Duration::from_secs(300);
const JWKS_COOLDOWN: Duration = Duration::from_secs(30);
// While the provider cannot be reached, known keys keep verifying tokens at most this
// long after their last successful fetch; a fetched key set always replaces them.
const JWKS_STALE_LIMIT: Duration = Duration::from_secs(3600);
const LOCAL_DEV_CLIENT_ID: &str = "local-dev";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Provider {
    Keycloak,
    Oidc,
}

/// `security.user.claims`
#[derive(Debug, Clone)]
pub struct UserClaims {
    pub uid: String,
    pub username: String,
    pub email: String,
    pub given_name: String,
    pub family_name: String,
}

impl Default for UserClaims {
    fn default() -> Self {
        Self {
            uid: "sub".into(),
            username: "preferred_username".into(),
            email: "email".into(),
            given_name: "given_name".into(),
            family_name: "family_name".into(),
        }
    }
}

/// `security.user`, `security.m2m.realm_url`, `security.profile` and the FRED_JWT_* settings.
#[derive(Debug, Clone)]
pub struct SecuritySettings {
    pub directory_delegation: crate::users::DirectoryDelegation,
    pub enabled: bool,
    pub provider: Provider,
    pub realm_url: String,
    pub client_id: String,
    pub audience: Option<String>,
    pub jwks_url: Option<String>,
    pub roles_claim: Option<Vec<String>>,
    pub claims: UserClaims,
    pub m2m_realm_url: Option<String>,
    pub profile_c3: bool,
    pub clock_skew_seconds: u64,
    pub max_token_lifetime_seconds: f64,
}

/// The authenticated person (`KeycloakUser`). `uid` is the OpenFGA user id.
#[derive(Clone)]
pub struct CurrentUser {
    pub uid: String,
    pub username: String,
    pub roles: Vec<String>,
    pub email: Option<String>,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub client_id: Option<String>,
    pub token_issuer: Option<String>,
    pub token_audiences: Vec<String>,
    pub token_type: Option<String>,
    pub service_account: bool,
    pub delegation_caller: bool,
    /// Validated JWT deadline, including configured skew; never persisted with uploads.
    pub valid_until: Option<f64>,
}

// Directly identifying data never reaches a log line.
impl fmt::Debug for CurrentUser {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("CurrentUser")
            .field("uid", &self.uid)
            .field("username", &self.username)
            .field("roles", &self.roles)
            .field("email", &self.email.as_ref().map(|_| "<redacted>"))
            .field("client_id", &self.client_id)
            .field("service_account", &self.service_account)
            .finish_non_exhaustive()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthError {
    MissingToken,
    SigningKey,
    Expired,
    Invalid,
    NegativeLifetime,
    LifetimeTooLong,
    InvalidClaims,
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let (detail, challenge) = match self {
            AuthError::MissingToken => ("No authentication token provided", "Bearer"),
            AuthError::SigningKey => ("Invalid token signature", "Bearer error='invalid_token'"),
            AuthError::Expired => (
                "Token has expired",
                "Bearer error='invalid_token', error_description='token expired'",
            ),
            AuthError::Invalid => ("Invalid token", "Bearer error='invalid_token'"),
            AuthError::NegativeLifetime => (
                "Token has invalid iat/exp claims",
                "Bearer error='invalid_token', error_description='exp before iat'",
            ),
            AuthError::LifetimeTooLong => (
                "Token lifetime exceeds the maximum permitted duration",
                "Bearer error='invalid_token', error_description='token lifetime too long'",
            ),
            AuthError::InvalidClaims => ("Invalid token claims", "Bearer error='invalid_token'"),
        };
        (
            StatusCode::UNAUTHORIZED,
            [(header::WWW_AUTHENTICATE, challenge)],
            Json(json!({ "detail": detail, "code": "unauthorized" })),
        )
            .into_response()
    }
}

/// Signing keys by `kid`, refreshed after five minutes or on an unknown `kid`.
struct Jwks {
    url: String,
    http: reqwest::Client,
    /// When the keys were fetched, and the signing keys by kid.
    cache: RwLock<(Option<Instant>, HashMap<String, DecodingKey>)>,
    /// When a fetch was last attempted, successful or not. Held during a fetch, so
    /// refetches run one at a time while cached keys stay readable.
    attempt: tokio::sync::Mutex<Option<Instant>>,
}

impl Jwks {
    fn new(url: String, http: reqwest::Client) -> Self {
        Self {
            url,
            http,
            cache: RwLock::new((None, HashMap::new())),
            attempt: tokio::sync::Mutex::new(None),
        }
    }

    async fn cached(&self, kid: &str, max_age: Duration) -> Option<DecodingKey> {
        let (fetched, keys) = &*self.cache.read().await;
        fetched
            .is_some_and(|t| t.elapsed() < max_age)
            .then(|| keys.get(kid).cloned())
            .flatten()
    }

    async fn key(&self, kid: &str) -> Result<DecodingKey> {
        if let Some(key) = self.cached(kid, JWKS_LIFESPAN).await {
            return Ok(key);
        }
        let mut attempt = self.attempt.lock().await;
        // Another request may have fetched while this one waited.
        if let Some(key) = self.cached(kid, JWKS_LIFESPAN).await {
            return Ok(key);
        }
        let stale = self.cached(kid, JWKS_STALE_LIMIT).await;
        if !may_fetch(attempt.map(|t| t.elapsed())) {
            return stale.context("unknown kid within the refetch cooldown");
        }
        *attempt = Some(Instant::now());
        let set = match self.fetch().await {
            Ok(set) => set,
            Err(error) => {
                if let Some(key) = stale {
                    tracing::warn!("[AUTH] JWKS refresh failed; serving a known signing key");
                    return Ok(key);
                }
                return Err(error);
            }
        };
        let keys = signing_keys(&set);
        let found = keys.get(kid).cloned();
        *self.cache.write().await = (Some(Instant::now()), keys);
        found.context("no signing key for kid")
    }

    async fn fetch(&self) -> Result<JwkSet> {
        Ok(self
            .http
            .get(&self.url)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?)
    }
}

/// PyJWKClient's cooldown, applied to every attempt: a failing realm is not hammered either.
fn may_fetch(since_last_attempt: Option<Duration>) -> bool {
    since_last_attempt.is_none_or(|elapsed| elapsed >= JWKS_COOLDOWN)
}

/// PyJWKClient keeps signing keys only; Keycloak also publishes an encryption key.
fn signing_keys(set: &JwkSet) -> HashMap<String, DecodingKey> {
    set.keys
        .iter()
        .filter(|jwk| {
            matches!(
                jwk.common.public_key_use,
                None | Some(PublicKeyUse::Signature)
            )
        })
        .filter_map(|jwk| {
            let kid = jwk.common.key_id.clone()?;
            DecodingKey::from_jwk(jwk).ok().map(|k| (kid, k))
        })
        .collect()
}

struct Verifier {
    settings: SecuritySettings,
    issuer: String,
    realm_issuers: Vec<String>,
    jwks: Jwks,
}

pub struct Authenticator {
    verifier: Option<Verifier>,
}

impl Authenticator {
    /// Resolves endpoints once; the c3 profile refuses to start without authentication.
    pub async fn start(settings: SecuritySettings) -> Result<Self> {
        if settings.profile_c3 && !settings.enabled {
            bail!(
                "C3 security profile violations (refusing to start): security.user.enabled must be true"
            );
        }
        if !settings.enabled {
            tracing::warn!("[AUTH] Authentication is DISABLED; every caller is the mock admin");
            return Ok(Self { verifier: None });
        }
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()?;
        let realm_url = settings.realm_url.trim_end_matches('/').to_string();
        let (issuer, jwks_url) = match settings.provider {
            Provider::Keycloak => (
                realm_url.clone(),
                settings
                    .jwks_url
                    .clone()
                    .unwrap_or_else(|| format!("{realm_url}/protocol/openid-connect/certs")),
            ),
            Provider::Oidc => discover(&http, &realm_url, settings.jwks_url.clone()).await?,
        };
        let mut realm_issuers: Vec<String> =
            [Some(&settings.realm_url), settings.m2m_realm_url.as_ref()]
                .into_iter()
                .flatten()
                .map(|u| u.trim_end_matches('/').to_string())
                .chain([realm_url])
                .collect();
        realm_issuers.sort();
        realm_issuers.dedup();
        tracing::info!(
            issuer,
            jwks_url,
            client_id = settings.client_id,
            "[AUTH] user authentication initialized"
        );
        Ok(Self {
            verifier: Some(Verifier {
                jwks: Jwks::new(jwks_url, http),
                issuer,
                realm_issuers,
                settings,
            }),
        })
    }

    pub fn enabled(&self) -> bool {
        self.verifier.is_some()
    }

    /// Directory grants use raw Keycloak subjects. Refuse a different identity mapping
    /// or realm rather than writing a tuple the authenticated target cannot hold.
    pub fn directory_subjects_match(&self, realm: &str) -> bool {
        self.verifier.as_ref().is_some_and(|v| {
            v.settings.provider == Provider::Keycloak
                && v.settings.claims.uid == "sub"
                && same_realm(&v.settings.realm_url, realm)
        })
    }

    pub async fn authenticate(&self, token: Option<&str>) -> Result<CurrentUser, AuthError> {
        let Some(v) = &self.verifier else {
            return Ok(mock_admin());
        };
        let Some(token) = token.filter(|t| !t.is_empty()) else {
            tracing::warn!("No Bearer token provided on secured endpoint");
            return Err(AuthError::MissingToken);
        };
        v.decode(token).await
    }

    /// The Python runtime may use its renewable workload bearer instead of a
    /// person's bearer. Only this receiver accepts the extra delegation audience;
    /// ordinary UI and embedded-agent authentication keeps its existing contract.
    pub(crate) async fn authenticate_runtime(
        &self,
        token: Option<&str>,
    ) -> Result<CurrentUser, AuthError> {
        let token = token
            .filter(|t| !t.is_empty())
            .ok_or(AuthError::MissingToken)?;
        // This contract always needs verified credentials, including on dev servers.
        let v = self.verifier.as_ref().ok_or(AuthError::Invalid)?;
        let delegation = &v.settings.directory_delegation;
        let caller = v
            .decode_with_audience(
                token,
                delegation
                    .accept_delegated_calls
                    .then_some(delegation.audience.as_str()),
            )
            .await?;
        let user_audience = v
            .settings
            .audience
            .as_deref()
            .unwrap_or(&v.settings.client_id);
        if !caller
            .token_audiences
            .iter()
            .any(|aud| aud == user_audience)
            && !self.accepts_runtime_delegation(&caller)
        {
            return Err(AuthError::Invalid);
        }
        Ok(caller)
    }

    /// Same trust predicate as fred-core is_delegation_caller. The asserted
    /// person never inherits the caller's roles or service-account privileges.
    pub(crate) fn accepts_runtime_delegation(&self, caller: &CurrentUser) -> bool {
        let Some(v) = &self.verifier else {
            return false;
        };
        let Some(client) = caller.client_id.as_deref().filter(|id| !id.is_empty()) else {
            return false;
        };
        let config = &v.settings.directory_delegation;
        config.accept_delegated_calls
            && caller.delegation_caller
            && caller.token_type.as_deref().is_none_or(|kind| {
                kind.eq_ignore_ascii_case("bearer") || kind.eq_ignore_ascii_case("at+jwt")
            })
            && caller.token_issuer.as_deref().is_some_and(|issuer| {
                v.realm_issuers
                    .iter()
                    .any(|trusted| trusted == issuer.trim_end_matches('/'))
            })
            && caller.token_audiences.contains(&config.audience)
            && client != v.settings.client_id
            && !config.user_clients.iter().any(|human| human == client)
            && (!config.service_accounts_only || caller.service_account)
    }
}

// Parse both sides so equivalent origins (including explicit default ports) match.
fn same_realm(left: &str, right: &str) -> bool {
    match (
        reqwest::Url::parse(left.trim_end_matches('/')),
        reqwest::Url::parse(right.trim_end_matches('/')),
    ) {
        (Ok(left), Ok(right)) => left == right,
        _ => false,
    }
}

impl Verifier {
    async fn decode(&self, token: &str) -> Result<CurrentUser, AuthError> {
        self.decode_with_audience(token, None).await
    }

    async fn decode_with_audience(
        &self,
        token: &str,
        delegation_audience: Option<&str>,
    ) -> Result<CurrentUser, AuthError> {
        let s = &self.settings;
        let kid = jsonwebtoken::decode_header(token).ok().and_then(|h| h.kid);
        let key = match kid {
            Some(kid) => self.jwks.key(&kid).await.ok(),
            None => None,
        };
        let Some(key) = key else {
            tracing::warn!("[AUTH] Could not retrieve a trusted JWT signing key");
            return Err(AuthError::SigningKey);
        };

        let user_audience = s.audience.clone().unwrap_or_else(|| s.client_id.clone());
        let mut validation = Validation::new(Algorithm::RS256);
        validation.leeway = s.clock_skew_seconds;
        validation.validate_nbf = true;
        let mut audiences = vec![user_audience.as_str()];
        audiences.extend(delegation_audience);
        validation.set_audience(&audiences);
        validation.set_issuer(&self.realm_issuers);
        validation
            .required_spec_claims
            .extend(["aud", "iss"].map(String::from));
        let payload = match jsonwebtoken::decode::<Map<String, Value>>(token, &key, &validation) {
            Ok(data) => data.claims,
            Err(e) if matches!(e.kind(), ErrorKind::ExpiredSignature) => {
                tracing::warn!("[AUTH] Access token expired");
                return Err(AuthError::Expired);
            }
            Err(_) => {
                tracing::error!("[AUTH] Invalid JWT token");
                return Err(AuthError::Invalid);
            }
        };

        check_times(
            &payload,
            now_seconds(),
            s.clock_skew_seconds,
            s.max_token_lifetime_seconds,
        )?;

        let roles_path = s.roles_claim.clone().unwrap_or_else(|| {
            vec![
                "resource_access".into(),
                s.client_id.clone(),
                "roles".into(),
            ]
        });
        let roles = match claim_path(&payload, &roles_path) {
            Some(Value::Array(items)) => items
                .iter()
                .filter_map(|r| r.as_str().map(String::from))
                .collect(),
            _ => Vec::new(),
        };
        let client_id = string(&payload, "azp").or_else(|| string(&payload, "client_id"));

        let identity = match payload.get(&s.claims.uid) {
            Some(Value::String(id)) if !id.trim().is_empty() => id.clone(),
            _ => {
                tracing::warn!("[AUTH] JWT token missing or invalid identity claim");
                return Err(AuthError::InvalidClaims);
            }
        };
        let uid = match s.provider {
            Provider::Oidc if Uuid::parse_str(&identity).is_err() => {
                let name = format!("{}#{identity}", self.issuer);
                Uuid::new_v5(&Uuid::NAMESPACE_URL, name.as_bytes()).to_string()
            }
            _ => identity,
        };

        let caller_path = s.directory_delegation.roles_path();
        let delegation_caller = claim_path(&payload, &caller_path)
            .and_then(Value::as_array)
            .is_some_and(|roles| {
                roles
                    .iter()
                    .any(|role| role.as_str() == Some(s.directory_delegation.caller_role.as_str()))
            });
        Ok(CurrentUser {
            delegation_caller,
            uid,
            username: string(&payload, &s.claims.username).unwrap_or_default(),
            roles,
            email: string(&payload, &s.claims.email),
            first_name: string(&payload, &s.claims.given_name),
            last_name: string(&payload, &s.claims.family_name),
            service_account: bears_service_account_markers(&payload, client_id.as_deref()),
            valid_until: payload
                .get("exp")
                .and_then(Value::as_f64)
                .map(|exp| exp + s.clock_skew_seconds as f64),
            client_id,
            token_issuer: string(&payload, "iss"),
            token_audiences: match payload.get("aud") {
                Some(Value::String(a)) if !a.is_empty() => vec![a.clone()],
                Some(Value::Array(items)) => items
                    .iter()
                    .filter_map(|a| a.as_str().map(String::from))
                    .collect(),
                _ => Vec::new(),
            },
            token_type: string(&payload, "typ"),
        })
    }
}

/// Generic OIDC discovery; the discovered issuer must equal the configured one.
async fn discover(
    http: &reqwest::Client,
    issuer: &str,
    jwks_url: Option<String>,
) -> Result<(String, String)> {
    let doc: Value = http
        .get(format!("{issuer}/.well-known/openid-configuration"))
        .send()
        .await
        .with_context(|| format!("OIDC discovery failed for issuer {issuer}"))?
        .error_for_status()
        .with_context(|| format!("OIDC discovery failed for issuer {issuer}"))?
        .json()
        .await
        .with_context(|| format!("OIDC discovery returned invalid JSON for {issuer}"))?;
    let discovered = doc["issuer"].as_str().unwrap_or_default();
    if discovered.trim_end_matches('/') != issuer {
        bail!("OIDC issuer mismatch: configured {issuer}, discovered {discovered}");
    }
    let jwks = jwks_url
        .or_else(|| doc["jwks_uri"].as_str().map(String::from))
        .with_context(|| format!("OIDC discovery did not provide jwks_uri for {issuer}"))?;
    Ok((issuer.to_string(), jwks))
}

/// Same identity fred-core returns when `security.user.enabled` is false.
fn mock_admin() -> CurrentUser {
    CurrentUser {
        uid: "admin".into(),
        username: "admin".into(),
        roles: vec!["admin".into()],
        email: Some("admin@mail.com".into()),
        first_name: None,
        last_name: None,
        client_id: Some(LOCAL_DEV_CLIENT_ID.into()),
        token_issuer: None,
        token_audiences: Vec::new(),
        token_type: None,
        service_account: false,
        delegation_caller: false,
        valid_until: None,
    }
}

/// Keycloak names a client's own service account `service-account-<client>`.
fn bears_service_account_markers(payload: &Map<String, Value>, client_id: Option<&str>) -> bool {
    let Some(client_id) = client_id.filter(|c| !c.is_empty()) else {
        return false;
    };
    let username = payload.get("preferred_username").and_then(Value::as_str);
    let named = payload
        .get("client_id")
        .or_else(|| payload.get("clientId"))
        .and_then(Value::as_str);
    username.is_some_and(|u| u.eq_ignore_ascii_case(&format!("service-account-{client_id}")))
        && named == Some(client_id)
}

fn claim_path<'a>(payload: &'a Map<String, Value>, path: &[String]) -> Option<&'a Value> {
    let (first, rest) = path.split_first()?;
    rest.iter()
        .try_fold(payload.get(first)?, |v, key| v.get(key))
}

fn string(payload: &Map<String, Value>, key: &str) -> Option<String> {
    payload.get(key).and_then(Value::as_str).map(String::from)
}

fn now_seconds() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// PyJWT refuses a non-integer or future `iat`; fred-core then caps `exp - iat`.
/// Stricter than fred-core on one point: `iat` is required, so the ceiling always applies.
fn check_times(
    payload: &Map<String, Value>,
    now: f64,
    leeway: u64,
    max_lifetime: f64,
) -> Result<(), AuthError> {
    let Some(iat) = payload.get("iat").and_then(Value::as_i64) else {
        tracing::warn!("[AUTH] JWT missing or non-integer iat");
        return Err(AuthError::Invalid);
    };
    let iat = iat as f64;
    if iat > now + leeway as f64 {
        tracing::warn!("[AUTH] JWT issued in the future");
        return Err(AuthError::Invalid);
    }
    let exp = payload
        .get("exp")
        .and_then(Value::as_f64)
        .ok_or(AuthError::Invalid)?;
    if exp - iat < 0.0 {
        tracing::warn!("[AUTH] JWT has negative lifetime");
        return Err(AuthError::NegativeLifetime);
    }
    if exp - iat > max_lifetime {
        tracing::warn!("[AUTH] JWT lifetime exceeds policy ceiling");
        return Err(AuthError::LifetimeTooLong);
    }
    Ok(())
}

/// `OAuth2PasswordBearer(auto_error=False)`: only `Authorization: Bearer <token>`.
pub(crate) fn bearer(parts: &Parts) -> Option<&str> {
    let value = parts.headers.get(header::AUTHORIZATION)?.to_str().ok()?;
    let (scheme, token) = value.split_once(' ')?;
    scheme
        .eq_ignore_ascii_case("bearer")
        .then_some(token.trim())
}

/// Route dependency equivalent to `Depends(get_current_user)`.
impl<S> FromRequestParts<S> for CurrentUser
where
    Arc<Authenticator>: axum::extract::FromRef<S>,
    S: Send + Sync,
{
    type Rejection = AuthError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let auth: Arc<Authenticator> = axum::extract::FromRef::from_ref(state);
        let user = auth.authenticate(bearer(parts)).await?;
        // As fred-core's bind_operation_context: every later line of the request names the user.
        tracing::Span::current().record("user_id", user.uid.as_str());
        Ok(user)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{EncodingKey, Header};
    use rsa::{
        RsaPrivateKey,
        pkcs1::{EncodeRsaPrivateKey, EncodeRsaPublicKey},
        rand_core::OsRng,
    };
    use std::sync::OnceLock;

    const REALM: &str = "http://localhost:8080/realms/app";
    const KID: &str = "test-kid";

    fn keys() -> &'static (EncodingKey, DecodingKey) {
        static KEYS: OnceLock<(EncodingKey, DecodingKey)> = OnceLock::new();
        KEYS.get_or_init(|| {
            let private = RsaPrivateKey::new(&mut OsRng, 2048).unwrap();
            let public = private.to_public_key();
            (
                EncodingKey::from_rsa_der(private.to_pkcs1_der().unwrap().as_bytes()),
                DecodingKey::from_rsa_der(public.to_pkcs1_der().unwrap().as_bytes()),
            )
        })
    }

    fn settings() -> SecuritySettings {
        SecuritySettings {
            directory_delegation: Default::default(),
            enabled: true,
            provider: Provider::Keycloak,
            realm_url: REALM.into(),
            client_id: "app".into(),
            audience: None,
            jwks_url: None,
            roles_claim: None,
            claims: UserClaims::default(),
            m2m_realm_url: None,
            profile_c3: false,
            clock_skew_seconds: 0,
            max_token_lifetime_seconds: 3600.0,
        }
    }

    fn verifier(settings: SecuritySettings) -> Verifier {
        let jwks = Jwks::new("http://unused".into(), reqwest::Client::new());
        let mut keys_by_kid = HashMap::new();
        keys_by_kid.insert(KID.to_string(), keys().1.clone());
        *jwks.cache.try_write().unwrap() = (Some(Instant::now()), keys_by_kid);
        Verifier {
            issuer: REALM.into(),
            realm_issuers: vec![REALM.into()],
            jwks,
            settings,
        }
    }

    fn now() -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64
    }

    fn token(claims: Value) -> String {
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some(KID.into());
        jsonwebtoken::encode(&header, &claims, &keys().0).unwrap()
    }

    fn bob(extra: Value) -> Value {
        let mut claims = json!({
            "sub": "0b7c2f8e-5a1d-4c3b-9e2f-1a2b3c4d5e6f",
            "preferred_username": "bob",
            "email": "bob@tsn.example",
            "azp": "app",
            "iss": REALM,
            "aud": "app",
            "iat": now(),
            "exp": now() + 300,
            "resource_access": { "app": { "roles": ["editor"] } },
        });
        claims
            .as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        claims
    }

    async fn decode(s: SecuritySettings, claims: Value) -> Result<CurrentUser, AuthError> {
        verifier(s).decode(&token(claims)).await
    }

    #[test]
    fn directory_realms_compare_normalized_urls() {
        assert!(same_realm(
            "https://host:443/realms/app/",
            "https://host/realms/app"
        ));
        assert!(same_realm(
            "http://host:80/realms/app",
            "http://host/realms/app"
        ));
        assert!(!same_realm(
            "https://host/realms/app",
            "https://host/realms/other"
        ));
        assert!(!same_realm(
            "https://host:8443/realms/app",
            "https://host/realms/app"
        ));
        assert!(!same_realm("invalid", "invalid"));
    }

    #[test]
    fn keeps_only_signing_keys_from_a_keycloak_jwks() {
        use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD as B64};
        use rsa::traits::PublicKeyParts;
        let public = RsaPrivateKey::new(&mut OsRng, 2048)
            .unwrap()
            .to_public_key();
        let (n, e) = (
            B64.encode(public.n().to_bytes_be()),
            B64.encode(public.e().to_bytes_be()),
        );
        let set: JwkSet = serde_json::from_value(json!({ "keys": [
            { "kid": "sig", "kty": "RSA", "alg": "RS256", "use": "sig", "n": n, "e": e },
            { "kid": "enc", "kty": "RSA", "alg": "RSA-OAEP", "use": "enc", "n": n, "e": e },
        ]}))
        .unwrap();
        let keys = signing_keys(&set);
        assert!(keys.contains_key("sig"));
        assert!(!keys.contains_key("enc"));
    }

    #[tokio::test]
    async fn maps_a_keycloak_ui_token() {
        let user = decode(settings(), bob(json!({}))).await.unwrap();
        assert_eq!(user.uid, "0b7c2f8e-5a1d-4c3b-9e2f-1a2b3c4d5e6f");
        assert_eq!(user.username, "bob");
        assert_eq!(user.roles, vec!["editor"]);
        assert_eq!(user.client_id.as_deref(), Some("app"));
        assert!(!user.service_account);
        assert!(!format!("{user:?}").contains("bob@tsn.example"));
    }

    // Proves: I10
    #[tokio::test]
    async fn rejects_expired_and_overlong_tokens() {
        let expired = bob(json!({ "iat": now() - 600, "exp": now() - 300 }));
        assert_eq!(
            decode(settings(), expired).await.unwrap_err(),
            AuthError::Expired
        );
        let overlong = bob(json!({ "exp": now() + 7200 }));
        assert_eq!(
            decode(settings(), overlong).await.unwrap_err(),
            AuthError::LifetimeTooLong
        );
        // PyJWT refuses a future iat before any lifetime check.
        let future = bob(json!({ "iat": now() + 600 }));
        assert_eq!(
            decode(settings(), future).await.unwrap_err(),
            AuthError::Invalid
        );
    }

    // Proves: I10
    #[tokio::test]
    async fn lifetime_ceiling_cannot_be_skipped() {
        let mut no_iat = bob(json!({ "exp": now() + 365 * 86400 }));
        no_iat.as_object_mut().unwrap().remove("iat");
        assert_eq!(
            decode(settings(), no_iat).await.unwrap_err(),
            AuthError::Invalid
        );
        let text_iat = bob(json!({ "iat": "x" }));
        assert_eq!(
            decode(settings(), text_iat).await.unwrap_err(),
            AuthError::Invalid
        );
        let fractional_iat = bob(json!({ "iat": now() as f64 + 0.5 }));
        assert_eq!(
            decode(settings(), fractional_iat).await.unwrap_err(),
            AuthError::Invalid
        );
    }

    #[test]
    fn negative_lifetime_is_refused() {
        let payload = json!({ "iat": 1000, "exp": 900 });
        let r = check_times(payload.as_object().unwrap(), 1000.0, 0, 3600.0);
        assert_eq!(r.unwrap_err(), AuthError::NegativeLifetime);
    }

    #[test]
    fn jwks_refetch_rules() {
        assert!(may_fetch(None));
        assert!(!may_fetch(Some(Duration::from_secs(10))));
        assert!(may_fetch(Some(Duration::from_secs(30))));
    }

    #[tokio::test]
    async fn known_keys_survive_an_unreachable_provider_within_the_stale_limit() {
        // Nothing listens on port 1: every refetch fails.
        let aged = |age: Duration| {
            let jwks = Jwks::new("http://127.0.0.1:1/certs".into(), reqwest::Client::new());
            let fetched = Instant::now()
                .checked_sub(age)
                .expect("monotonic clock older than the stale limit");
            *jwks.cache.try_write().unwrap() = (
                Some(fetched),
                HashMap::from([(KID.to_string(), keys().1.clone())]),
            );
            jwks
        };
        let expired = aged(JWKS_LIFESPAN + Duration::from_secs(1));
        assert!(
            expired.key(KID).await.is_ok(),
            "failed refetch serves a known kid"
        );
        assert!(expired.key(KID).await.is_ok(), "so does the cooldown");
        assert!(expired.key("unknown").await.is_err());
        let too_old = aged(JWKS_STALE_LIMIT + Duration::from_secs(1));
        assert!(too_old.key(KID).await.is_err());
    }

    #[tokio::test]
    async fn a_failed_fetch_starts_the_cooldown_too() {
        // Nothing listens on port 1: the first attempt fails, the second is not even tried.
        let jwks = Jwks::new("http://127.0.0.1:1/certs".into(), reqwest::Client::new());
        let first = jwks.key("any").await.unwrap_err().to_string();
        let second = jwks.key("any").await.unwrap_err().to_string();
        assert!(!first.contains("cooldown"), "{first}");
        assert!(second.contains("cooldown"), "{second}");
    }

    // Proves: I10
    #[tokio::test]
    async fn rejects_missing_kid_and_bad_signature() {
        // An unknown kid would refetch the JWKS; a missing kid fails before any network call.
        let v = verifier(settings());
        let header = Header::new(Algorithm::RS256);
        let t = jsonwebtoken::encode(&header, &bob(json!({})), &keys().0).unwrap();
        assert_eq!(v.decode(&t).await.unwrap_err(), AuthError::SigningKey);

        let hs = Header {
            kid: Some(KID.into()),
            ..Header::new(Algorithm::HS256)
        };
        let forged =
            jsonwebtoken::encode(&hs, &bob(json!({})), &EncodingKey::from_secret(b"x")).unwrap();
        assert_eq!(v.decode(&forged).await.unwrap_err(), AuthError::Invalid);
    }

    // Proves: I10
    #[tokio::test]
    async fn issuer_and_audience_are_always_checked() {
        // Without a security profile: a token of another client or realm never authenticates.
        assert!(!settings().profile_c3);
        let wrong_aud = bob(json!({ "aud": "account" }));
        let wrong_iss = bob(json!({ "iss": "http://evil/realms/app" }));
        let mut no_aud = bob(json!({}));
        no_aud.as_object_mut().unwrap().remove("aud");
        let mut no_iss = bob(json!({}));
        no_iss.as_object_mut().unwrap().remove("iss");
        for claims in [wrong_aud, wrong_iss, no_aud, no_iss] {
            assert_eq!(
                decode(settings(), claims).await.unwrap_err(),
                AuthError::Invalid
            );
        }
        let configured = SecuritySettings {
            audience: Some("control-plane".into()),
            ..settings()
        };
        assert!(
            decode(
                configured,
                bob(json!({ "aud": ["account", "control-plane"] }))
            )
            .await
            .is_ok()
        );
    }

    #[tokio::test]
    async fn oidc_subjects_become_stable_uuids() {
        let oidc = SecuritySettings {
            provider: Provider::Oidc,
            ..settings()
        };
        let user = decode(oidc, bob(json!({ "sub": "bob@idp" })))
            .await
            .unwrap();
        let expected = Uuid::new_v5(&Uuid::NAMESPACE_URL, format!("{REALM}#bob@idp").as_bytes());
        assert_eq!(user.uid, expected.to_string());
        let missing = bob(json!({ "sub": "" }));
        assert_eq!(
            decode(settings(), missing).await.unwrap_err(),
            AuthError::InvalidClaims
        );
    }

    #[tokio::test]
    async fn service_account_markers_and_disabled_mode() {
        let sa = bob(
            json!({ "preferred_username": "service-account-ingest", "azp": "ingest", "client_id": "ingest" }),
        );
        assert!(decode(settings(), sa).await.unwrap().service_account);

        let disabled = Authenticator { verifier: None };
        let user = disabled.authenticate(None).await.unwrap();
        assert_eq!(
            (user.uid.as_str(), user.client_id.as_deref()),
            ("admin", Some("local-dev"))
        );

        let enabled = Authenticator {
            verifier: Some(verifier(settings())),
        };
        assert_eq!(
            enabled.authenticate(None).await.unwrap_err(),
            AuthError::MissingToken
        );
    }
}
