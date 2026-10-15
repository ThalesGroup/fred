//! A wholly disposable Keycloak container; administrator credentials exist only in it.
use serde_json::{Value, json};
use std::time::Duration;

pub struct Keycloak {
    name: String,
    pub base: String,
    token: String,
    http: reqwest::Client,
}
impl Drop for Keycloak {
    fn drop(&mut self) {
        let _ = std::process::Command::new("docker")
            .args(["rm", "-f", &self.name])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
}
impl Keycloak {
    pub async fn start() -> Self {
        let name = format!("manager-it-keycloak-{}", uuid::Uuid::new_v4());
        let image = std::env::var("INTEGRATION_KEYCLOAK_IMAGE")
            .unwrap_or_else(|_| "mirror.gcr.io/keycloak/keycloak:26.3.0".into());
        let output = tokio::process::Command::new("docker")
            .args([
                "run",
                "-d",
                "--rm",
                "--name",
                &name,
                "-e",
                "KC_BOOTSTRAP_ADMIN_USERNAME=admin",
                "-e",
                "KC_BOOTSTRAP_ADMIN_PASSWORD=it-admin",
                "-p",
                "127.0.0.1::8080",
                &image,
                "start-dev",
            ])
            .output()
            .await
            .unwrap();
        assert!(
            output.status.success(),
            "Keycloak container could not start"
        );
        let mut kc = Self {
            name,
            base: String::new(),
            token: String::new(),
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(5))
                .build()
                .unwrap(),
        };
        let output = tokio::process::Command::new("docker")
            .args(["port", &kc.name, "8080/tcp"])
            .output()
            .await
            .unwrap();
        kc.base = format!(
            "http://{}",
            String::from_utf8(output.stdout).unwrap().trim()
        );
        tokio::time::timeout(Duration::from_secs(90), async {
            loop {
                if kc
                    .http
                    .get(format!("{}/realms/master", kc.base))
                    .send()
                    .await
                    .is_ok_and(|r| r.status().is_success())
                {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(200)).await;
            }
        })
        .await
        .expect("Keycloak readiness");
        kc.token = kc
            .password_token("master", "admin-cli", "admin", "it-admin")
            .await;
        kc
    }
    pub async fn password_token(
        &self,
        realm: &str,
        client: &str,
        user: &str,
        password: &str,
    ) -> String {
        let response = self
            .http
            .post(format!(
                "{}/realms/{realm}/protocol/openid-connect/token",
                self.base
            ))
            .form(&[
                ("grant_type", "password"),
                ("client_id", client),
                ("username", user),
                ("password", password),
            ])
            .send()
            .await
            .unwrap();
        let status = response.status();
        let reply: Value = response.json().await.unwrap();
        assert!(
            status.is_success(),
            "test login {user}: {}",
            reply["error_description"]
        );
        reply["access_token"].as_str().unwrap().into()
    }
    pub async fn get(&self, path: &str) -> Value {
        self.http
            .get(format!("{}{path}", self.base))
            .bearer_auth(&self.token)
            .send()
            .await
            .unwrap()
            .error_for_status()
            .unwrap()
            .json()
            .await
            .unwrap()
    }
    pub async fn post(&self, path: &str, value: Value) {
        self.http
            .post(format!("{}{path}", self.base))
            .bearer_auth(&self.token)
            .json(&value)
            .send()
            .await
            .unwrap()
            .error_for_status()
            .unwrap();
    }
    pub async fn configure(&self) -> String {
        self.post("/admin/realms",json!({"realm":"app","enabled":true,"clients":[
            {"clientId":"app","publicClient":true,"directAccessGrantsEnabled":true,"protocolMappers":[{"name":"audience","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","config":{"included.client.audience":"app","access.token.claim":"true","id.token.claim":"false"}}]},
            {"clientId":"fred-manager","secret":"it-manager","serviceAccountsEnabled":true,"publicClient":false}
        ],"users":[{"username":"root","enabled":true,"email":"root@example.com","firstName":"Root","lastName":"Admin","credentials":[{"type":"password","value":"it-root","temporary":false}]}]})).await;
        let clients = self.get("/admin/realms/app/clients").await;
        let client = |name: &str| {
            clients
                .as_array()
                .unwrap()
                .iter()
                .find(|c| c["clientId"] == name)
                .unwrap()["id"]
                .as_str()
                .unwrap()
        };
        let service = self
            .get(&format!(
                "/admin/realms/app/clients/{}/service-account-user",
                client("fred-manager")
            ))
            .await;
        let management = client("realm-management");
        let roles = self
            .get(&format!("/admin/realms/app/clients/{management}/roles"))
            .await;
        let grants: Vec<_> = roles
            .as_array()
            .unwrap()
            .iter()
            .filter(|r| {
                ["query-users", "view-users", "manage-users"].contains(&r["name"].as_str().unwrap())
            })
            .cloned()
            .collect();
        assert_eq!(grants.len(), 3);
        self.post(
            &format!(
                "/admin/realms/app/users/{}/role-mappings/clients/{management}",
                service["id"].as_str().unwrap()
            ),
            json!(grants),
        )
        .await;
        format!("{}/realms/app", self.base)
    }

    /// Enable the real authorization-code/PKCE browser login for one local test origin.
    #[allow(dead_code)]
    pub async fn allow_browser(&self, origin: &str) {
        let clients = self.get("/admin/realms/app/clients?clientId=app").await;
        let mut client = clients[0].clone();
        client["standardFlowEnabled"] = json!(true);
        client["redirectUris"] = json!([format!("{origin}/*")]);
        client["webOrigins"] = json!([origin]);
        self.http
            .put(format!(
                "{}/admin/realms/app/clients/{}",
                self.base,
                client["id"].as_str().unwrap()
            ))
            .bearer_auth(&self.token)
            .json(&client)
            .send()
            .await
            .unwrap()
            .error_for_status()
            .unwrap();
    }
}
