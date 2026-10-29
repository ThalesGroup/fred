//! Local Keycloak protocol fixture; subjects and passwords never leave this server.
use axum::{
    Json, Router,
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, post},
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use control_plane::{auth::Authenticator, config::Configuration, keycloak::Directory};
use jsonwebtoken::{Algorithm, EncodingKey, Header};
use rsa::{RsaPrivateKey, pkcs1::EncodeRsaPrivateKey, rand_core::OsRng, traits::PublicKeyParts};
use serde_json::{Value, json};
use std::{collections::BTreeMap, sync::Arc};
use tokio::sync::Mutex;

#[derive(Default)]
pub struct Gate {
    pub entered: tokio::sync::Notify,
    pub release: tokio::sync::Notify,
}
#[derive(Default)]
pub struct Control {
    pub worker_token: Option<String>,
    pub worker_token_requests: usize,
    pub subject_delay: bool,
    pub subject_lookups: Vec<String>,
    pub subject_active: usize,
    pub subject_peak: usize,
    pub lookup_gate: Option<Arc<Gate>>,
    pub create_gate: Option<Arc<Gate>>,
    pub created: Vec<Value>,
    pub fail_create: bool,
    pub conflict_create: bool,
    pub lookup_ambiguous: bool,
    pub lookup_inexact: bool,
    pub lookup_slow: bool,
}

pub struct IdentityServer {
    pub control: Arc<Mutex<Control>>,
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
        let control = Arc::new(Mutex::new(Control::default()));
        let lookup_control = control.clone();
        let create_control = control.clone();
        let subject_control = control.clone();
        let token_control = control.clone();
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
                post(move |axum::Form(form): axum::Form<BTreeMap<String, String>>| {
                    let control = token_control.clone();
                    async move {
                        let mut c = control.lock().await;
                        if c.worker_token.is_some() {
                            assert_eq!(form.get("grant_type").map(String::as_str), Some("client_credentials"));
                            assert_eq!(form.get("client_id").map(String::as_str), Some("manager-worker"));
                            assert_eq!(form.get("client_secret").map(String::as_str), Some("fixture"));
                            assert_eq!(form.get("audience").map(String::as_str), Some("app"));
                            c.worker_token_requests += 1;
                        }
                        Json(json!({"access_token":c.worker_token.as_deref().unwrap_or("service-token"), "expires_in":300}))
                    }
                }),
            )
            .route(
                "/admin/realms/app/users",
                get(
                    move |State(users): State<Arc<Mutex<BTreeMap<String, String>>>>,
                          Query(query): Query<BTreeMap<String, String>>| {
                        let control = lookup_control.clone();
                        async move {
                            assert_eq!(query["exact"], "true");
                            let gate = control.lock().await.lookup_gate.take();
                            if let Some(gate) = gate {
                                gate.entered.notify_one();
                                gate.release.notified().await;
                            }
                            let control = control.lock().await;
                            if control.lookup_slow {
                                tokio::time::sleep(std::time::Duration::from_secs(6)).await;
                            }
                            let first: usize = query["first"].parse().unwrap();
                            if let Some(email) = query.get("email") {
                                let values: Vec<_> = control
                                    .created
                                    .iter()
                                    .filter(|u| {
                                        u["email"]
                                            .as_str()
                                            .is_some_and(|v| v.eq_ignore_ascii_case(email))
                                    })
                                    .map(|u| json!({"id":"email-holder", "username":u["username"]}))
                                    .collect();
                                return Json(values);
                            }
                            // A deliberately capped page size exercises continuation after a short page.
                            let mut values: Vec<_> = users
                                .lock()
                                .await
                                .iter()
                                .filter(|(_, name)| *name == &query["username"])
                                .map(|(id, name)| json!({"id":id,"username":name}))
                                .collect();
                            if control.lookup_ambiguous {
                                values = vec![
                                    json!({"id":"one","username":query["username"]}),
                                    json!({"id":"two","username":query["username"]}),
                                ];
                            }
                            if control.lookup_inexact {
                                values = vec![json!({"id":"other","username":"not-requested"})];
                            }
                            Json(values.into_iter().skip(first).take(1).collect::<Vec<_>>())
                        }
                    },
                )
                .post(
                    move |State(users): State<Arc<Mutex<BTreeMap<String, String>>>>,
                          Json(body): Json<Value>| {
                        let control = create_control.clone();
                        async move {
                            let mut control = control.lock().await;
                            if control.fail_create {
                                return (
                                    StatusCode::INTERNAL_SERVER_ERROR,
                                    Json(json!({"error":"private-password"})),
                                );
                            }
                            let mut users = users.lock().await;
                            if users
                                .values()
                                .any(|n| n == body["username"].as_str().unwrap())
                            {
                                return (StatusCode::CONFLICT, Json(json!({})));
                            }
                            let id = uuid::Uuid::new_v4().to_string();
                            users.insert(id, body["username"].as_str().unwrap().into());
                            control.created.push(body);
                            let conflict = control.conflict_create;
                            let gate = control.create_gate.take();
                            drop(users);
                            drop(control);
                            if let Some(gate) = gate {
                                gate.entered.notify_one();
                                gate.release.notified().await;
                            }
                            (
                                if conflict {
                                    StatusCode::CONFLICT
                                } else {
                                    StatusCode::CREATED
                                },
                                Json(json!({})),
                            )
                        }
                    },
                ),
            )
            .route(
                "/admin/realms/app/users/{id}",
                get(
                    move |State(users): State<Arc<Mutex<BTreeMap<String, String>>>>,
                          Path(id): Path<String>| {
                        let control = subject_control.clone();
                        async move {
                            let delayed = {
                                let mut control = control.lock().await;
                                control.subject_lookups.push(id.clone());
                                control.subject_active += 1;
                                control.subject_peak =
                                    control.subject_peak.max(control.subject_active);
                                control.subject_delay
                            };
                            if delayed {
                                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                            }
                            control.lock().await.subject_active -= 1;
                            if id == "unavailable" {
                                return (
                                    StatusCode::SERVICE_UNAVAILABLE,
                                    Json(json!({"error":"secret-echo"})),
                                );
                            }
                            match users.lock().await.get(&id) {
                                Some(name) => {
                                    (StatusCode::OK, Json(json!({"id":id, "username":name})))
                                }
                                None => (StatusCode::NOT_FOUND, Json(json!({}))),
                            }
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
            control,
            realm,
            users,
            key,
            task,
        }
    }
    pub fn directory(&self) -> Directory {
        Directory::new(&self.realm, "control-plane", "private-secret".into()).unwrap()
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

pub mod fga_proxy;
pub mod real_keycloak;

/// Create through HTTP with a separate governance owner, then explicitly grant content
/// to the business administrator. The temporary platform grant leaves bootstrap untouched.
pub async fn member_organization(
    pool: &sqlx::PgPool,
    fga: &control_plane::fga::Fga,
    name: &str,
    admin: &str,
) -> Result<control_plane::domain::Space, (u16, serde_json::Value)> {
    use control_plane::{
        api::{AppState, routes},
        db,
        domain::Role,
        fga::Scope,
        roles::PlatformRole,
        spaces,
    };
    use serde_json::json;
    use tower::ServiceExt;

    let identity = IdentityServer::start().await;
    let owner = format!("{admin}-owner");
    for user in [owner.as_str(), admin] {
        identity.users.lock().await.insert(user.into(), user.into());
    }
    let operator = format!("fixture-platform-{}", uuid::Uuid::new_v4());
    let mut guard = fga.guard(&[Scope::Platform]).await.unwrap();
    fga.write_platform(&mut guard, &operator, PlatformRole::PlatformOwner, true)
        .await
        .unwrap();
    let app = routes(AppState {
        agent_catalog: Default::default(),
        pool: pool.clone(),
        fga: fga.clone(),
        auth: std::sync::Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let response = app
        .oneshot(
            axum::http::Request::builder()
                .method("POST")
                .uri("/admin/organizations")
                .header(
                    "authorization",
                    format!("Bearer {}", identity.token(&operator)),
                )
                .header("content-type", "application/json")
                .body(axum::body::Body::from(
                    json!({"name":name,"owner_username":owner,"admin_usernames":[admin]})
                        .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    let mut guard = fga.guard(&[Scope::Platform]).await.unwrap();
    fga.write_platform(&mut guard, &operator, PlatformRole::PlatformOwner, false)
        .await
        .unwrap();
    let status = response.status().as_u16();
    let bytes = axum::body::to_bytes(response.into_body(), 1024 * 1024)
        .await
        .unwrap();
    let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    if status != 201 {
        return Err((status, body));
    }
    let id = uuid::Uuid::parse_str(body["id"].as_str().unwrap()).unwrap();
    spaces::grant(
        pool,
        fga,
        &control_plane::users::Directory::Keycloak(Some(&identity.directory())),
        admin,
        id,
        Role::Member,
        admin,
    )
    .await
    .unwrap();
    Ok(db::space(pool, id).await.unwrap().into())
}
