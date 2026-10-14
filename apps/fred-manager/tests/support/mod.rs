//! Local Keycloak protocol fixture; subjects and passwords never leave this server.
use axum::{
    Json, Router,
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use fred_manager::{auth::Authenticator, config::Configuration, keycloak::Directory};
use jsonwebtoken::{Algorithm, EncodingKey, Header};
use rsa::{RsaPrivateKey, pkcs1::EncodeRsaPrivateKey, rand_core::OsRng, traits::PublicKeyParts};
use serde_json::{Value, json};
use std::{collections::BTreeMap, sync::Arc};
use tokio::sync::Mutex;

pub struct IdentityServer {
    pub realm: String,
    pub users: Arc<Mutex<BTreeMap<String, String>>>,
    pub key: EncodingKey,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for IdentityServer {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl IdentityServer {
    pub async fn start() -> Self {
        let private = RsaPrivateKey::new(&mut OsRng, 2048).unwrap();
        let public = private.to_public_key();
        let jwks = json!({"keys": [{"kty":"RSA", "alg":"RS256", "use":"sig", "kid":"fixture", "n":URL_SAFE_NO_PAD.encode(public.n().to_bytes_be()), "e":URL_SAFE_NO_PAD.encode(public.e().to_bytes_be())}]});
        let key = EncodingKey::from_rsa_der(private.to_pkcs1_der().unwrap().as_bytes());
        let users = Arc::new(Mutex::new(BTreeMap::<String, String>::new()));
        let app = Router::new()
            .route(
                "/realms/app/protocol/openid-connect/certs",
                get(move || {
                    let jwks = jwks.clone();
                    async move { Json(jwks) }
                }),
            )
            .route(
                "/realms/app/protocol/openid-connect/token",
                post(|| async { Json(json!({"access_token":"service-token", "expires_in":300})) }),
            )
            .route(
                "/admin/realms/app/users/{id}",
                get(
                    |State(users): State<Arc<Mutex<BTreeMap<String, String>>>>,
                     Path(id): Path<String>| async move {
                        if id == "unavailable" {
                            return (
                                StatusCode::SERVICE_UNAVAILABLE,
                                Json(json!({"error":"secret-echo"})),
                            );
                        }
                        match users.lock().await.get(&id) {
                            Some(name) => (StatusCode::OK, Json(json!({"id":id, "username":name}))),
                            None => (StatusCode::NOT_FOUND, Json(json!({}))),
                        }
                    },
                ),
            )
            .with_state(users.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let realm = format!("http://{}/realms/app", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        Self {
            realm,
            users,
            key,
            task,
        }
    }
    pub fn directory(&self) -> Directory {
        Directory::new(&self.realm, "fred-manager", "private-secret".into()).unwrap()
    }
    pub async fn auth(&self) -> Authenticator {
        let mut config: Configuration =
            serde_yaml_ng::from_str(include_str!("../../config/configuration.yaml")).unwrap();
        config.security.user.realm_url = self.realm.clone();
        config.security.m2m = None;
        Authenticator::start(config.security().unwrap())
            .await
            .unwrap()
    }
    pub fn token(&self, user: &str) -> String {
        let now = chrono::Utc::now().timestamp();
        self.sign(json!({"sub":user, "preferred_username":user, "iss":self.realm, "aud":"app", "iat":now, "exp":now+300}))
    }
    pub fn sign(&self, claims: Value) -> String {
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some("fixture".into());
        jsonwebtoken::encode(&header, &claims, &self.key).unwrap()
    }
}
