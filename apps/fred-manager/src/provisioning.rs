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

//! Additive provisioning. Preflight is read-only; each identity mutation holds the
//! platform lock, and space reconciliation holds platform then organization locks.
//! There is no distributed rollback: replay resolves identities and committed IDs.

use crate::{
    auth::Authenticator,
    bootstrap, db,
    domain::{Role, Space, SpaceKind},
    fga::{Fga, Tuple},
    keycloak::Directory,
    logging, platform,
    roles::PlatformRole,
    spaces,
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawBundle {
    organization: Organization,
    users: Vec<RawUser>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Organization {
    name: String,
    admins: Vec<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawUser {
    username: String,
    email: Option<String>,
    first_name: Option<String>,
    last_name: Option<String>,
    password: Option<String>,
    #[serde(default)]
    teams: Vec<String>,
    #[serde(default, deserialize_with = "unique_roles")]
    team_roles: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    platform_roles: Vec<String>,
}
// Unlike a generic map, malformed duplicate declarations cannot silently overwrite roles.
fn unique_roles<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<BTreeMap<String, Vec<String>>, D::Error> {
    struct Visitor;
    impl<'de> serde::de::Visitor<'de> for Visitor {
        type Value = BTreeMap<String, Vec<String>>;
        fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
            f.write_str("unique role declarations")
        }
        fn visit_map<M: serde::de::MapAccess<'de>>(
            self,
            mut map: M,
        ) -> std::result::Result<Self::Value, M::Error> {
            let mut roles = BTreeMap::new();
            while let Some((key, value)) = map.next_entry::<String, Vec<String>>()? {
                if roles.insert(key, value).is_some() {
                    return Err(serde::de::Error::custom("duplicate team role"));
                }
            }
            Ok(roles)
        }
    }
    deserializer.deserialize_map(Visitor)
}
struct Entry {
    identity: RawUser,
    teams: BTreeMap<String, Vec<Role>>,
    platform: BTreeSet<PlatformRole>,
}
/// Validated input intentionally has no Debug/Serialize implementation: it holds passwords.
pub struct Bundle {
    organization: Organization,
    users: Vec<Entry>,
}

fn valid_name(value: &str) -> bool {
    !value.trim().is_empty() && !value.chars().any(char::is_control)
}
impl Bundle {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        // Serde's error can include an unknown field or value supplied near a password.
        let raw: RawBundle = serde_json::from_slice(bytes)
            .map_err(|_| anyhow::anyhow!("invalid provisioning JSON or unknown field"))?;
        ensure!(
            valid_name(&raw.organization.name),
            "organization name must be nonempty"
        );
        ensure!(
            !raw.organization.admins.is_empty(),
            "organization admins must be nonempty"
        );
        let mut names = BTreeSet::new();
        let mut users = Vec::new();
        for user in raw.users {
            ensure!(valid_name(&user.username), "username must be nonempty");
            ensure!(names.insert(user.username.clone()), "duplicate username");
            let mut teams = BTreeMap::<String, Vec<Role>>::new();
            for (role, targets) in &user.team_roles {
                let role = match role.as_str() {
                    "team_member" => Role::Member,
                    "team_editor" => Role::Editor,
                    "team_admin" => Role::Admin,
                    "team_analyst" => Role::Analyst,
                    _ => bail!("unknown or non-assignable team role"),
                };
                for team in targets {
                    ensure!(valid_name(team), "team name must be nonempty");
                    let roles = teams.entry(team.clone()).or_default();
                    if !roles.contains(&role) {
                        roles.push(role);
                    }
                }
            }
            for team in &user.teams {
                ensure!(valid_name(team), "team name must be nonempty");
                teams
                    .entry(team.clone())
                    .or_insert_with(|| vec![Role::Member]);
            }
            let platform = user
                .platform_roles
                .iter()
                .map(|r| PlatformRole::parse(r).context("unknown or non-assignable platform role"))
                .collect::<Result<_>>()?;
            users.push(Entry {
                identity: user,
                teams,
                platform,
            });
        }
        ensure!(
            raw.organization.admins.iter().all(|a| names.contains(a)),
            "organization admin must name a bundle user"
        );
        Ok(Self {
            organization: raw.organization,
            users,
        })
    }
    fn has_admin_grant(&self) -> bool {
        self.users
            .iter()
            .any(|u| u.platform.contains(&PlatformRole::PlatformAdmin))
    }
    fn teams(&self) -> BTreeSet<&str> {
        self.users
            .iter()
            .flat_map(|u| u.teams.keys().map(String::as_str))
            .collect()
    }
    fn declares_admin(&self, team: &str) -> bool {
        self.users
            .iter()
            .any(|u| u.teams.get(team).is_some_and(|r| r.contains(&Role::Admin)))
    }
}

#[derive(Debug, Default, Serialize)]
pub struct Report {
    pub identities_resolved: usize,
    pub identities_created: usize,
    pub spaces_reconciled: usize,
    pub grants_acknowledged: usize,
}
impl std::fmt::Display for Report {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "identities_resolved={}, identities_created={}, spaces_reconciled={}, grants_acknowledged={}",
            self.identities_resolved,
            self.identities_created,
            self.spaces_reconciled,
            self.grants_acknowledged
        )
    }
}

pub struct Importer<'a> {
    pub pool: &'a PgPool,
    pub fga: &'a Fga,
    pub directory: &'a Directory,
    pub auth: &'a Authenticator,
    pub bearer: &'a str,
}
impl Importer<'_> {
    /// Verify token again at every mutation boundary, including after waiting for locks.
    async fn authorize(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        bundle: &Bundle,
    ) -> Result<String> {
        ensure!(
            self.auth.directory_subjects_match(self.directory.realm()),
            "import requires enabled Keycloak subject authentication in the directory realm"
        );
        let caller = self
            .auth
            .authenticate(Some(self.bearer))
            .await
            .map_err(|_| anyhow::anyhow!("invalid or expired operator bearer"))?;
        platform::require_admin(self.fga, &caller.uid).await?;
        if bundle.has_admin_grant() {
            platform::require_root(tx, &caller.uid).await?;
        }
        Ok(caller.uid)
    }

    /// Every predictable input, identity and space conflict is checked before creating
    /// the first identity. State is reread under locks for each mutation phase.
    async fn preflight(&self, bundle: &Bundle) -> Result<()> {
        let mut tx = bootstrap::locked(self.pool).await?;
        self.authorize(&mut tx, bundle).await?;
        self.validate_spaces(&mut tx, bundle).await?;
        tx.rollback().await?; // Do not block revocations during read-only directory traversal.
        for entry in &bundle.users {
            let user = &entry.identity;
            if self
                .directory
                .find_username(&user.username)
                .await?
                .is_none()
            {
                ensure!(
                    user.password.as_ref().is_some_and(|p| !p.is_empty()),
                    "missing identity requires a password"
                );
            }
        }
        Ok(())
    }

    async fn validate_spaces(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        bundle: &Bundle,
    ) -> Result<Option<Space>> {
        let org = db::named_space(&mut **tx, None, &bundle.organization.name).await?;
        if let Some(org) = &org {
            ensure!(
                org.kind == SpaceKind::Organization && org.personal_owner.is_none(),
                "incompatible organization collision"
            );
            spaces::lock_organization(tx, org).await?;
        }
        for name in bundle.teams() {
            let team = if let Some(org) = &org {
                db::named_space(&mut **tx, Some(org.id), name).await?
            } else {
                None
            };
            if let Some(team) = team {
                ensure!(
                    team.kind == SpaceKind::Team && team.personal_owner.is_none(),
                    "incompatible or personal team collision"
                );
            } else {
                ensure!(
                    bundle.declares_admin(name),
                    "new team requires a declared team admin"
                );
            }
        }
        Ok(org)
    }

    pub async fn run(&self, bundle: &Bundle) -> Result<Report> {
        let mut report = Report::default();
        // Error causes from SQL may contain user-supplied values. Return only safe phase
        // and counters; upstream bodies and bundle values never enter the error chain.
        if let Err(error) = self.preflight(bundle).await {
            // Our input/authorization messages are static; SQL/dependency diagnostics are not.
            let reason = match error.to_string().as_str() {
                "missing identity requires a password" => "missing identity requires a password",
                "new team requires a declared team admin" => {
                    "new team requires a declared team admin"
                }
                "incompatible or personal team collision" => {
                    "incompatible or personal team collision"
                }
                "forbidden" => "forbidden",
                _ => "authentication, directory or state validation failed",
            };
            bail!(
                "provisioning preflight failed: {reason}; {report}; correct the cause and replay"
            );
        }
        let mut subjects = BTreeMap::new();
        for entry in &bundle.users {
            let result = async {
                let mut tx = bootstrap::locked(self.pool).await?;
                self.authorize(&mut tx, bundle).await?;
                let user = &entry.identity;
                let (resolved, created) = self
                    .directory
                    .ensure_user(
                        &user.username,
                        user.password.as_deref(),
                        user.email.as_deref(),
                        user.first_name.as_deref(),
                        user.last_name.as_deref(),
                    )
                    .await?;
                report.identities_resolved += 1;
                report.identities_created += usize::from(created);
                subjects.insert(user.username.clone(), resolved.id);
                tx.commit().await?;
                Ok::<_, anyhow::Error>(())
            }
            .await;
            if result.is_err() {
                bail!(
                    "provisioning identities failed; {report}; correct the cause and replay (acknowledgments may be incomplete)"
                );
            }
        }
        if self
            .reconcile(bundle, &subjects, &mut report)
            .await
            .is_err()
        {
            bail!(
                "provisioning roles/spaces failed; {report}; correct the cause and replay (acknowledgments may be incomplete)"
            );
        }
        Ok(report)
    }

    async fn reconcile(
        &self,
        bundle: &Bundle,
        subjects: &BTreeMap<String, String>,
        report: &mut Report,
    ) -> Result<()> {
        let mut tx = bootstrap::locked(self.pool).await?;
        self.authorize(&mut tx, bundle).await?;
        let existing = self.validate_spaces(&mut tx, bundle).await?;
        // validate_spaces may wait for the organization lock after the platform check.
        let actor = self.authorize(&mut tx, bundle).await?;
        let org = existing.unwrap_or_else(|| {
            let id = Uuid::new_v4();
            Space {
                id,
                name: bundle.organization.name.clone(),
                kind: SpaceKind::Organization,
                parent_id: None,
                personal_owner: None,
                path: vec![id],
            }
        });
        // A fresh organization cannot have other mutations yet; lock it before insertion.
        spaces::lock_organization(&mut tx, &org).await?;
        if db::named_space(&mut *tx, None, &org.name).await?.is_none() {
            db::insert_space(&mut tx, &org).await?;
        }
        let mut parent = Vec::new();
        for entry in &bundle.users {
            let user = &subjects[&entry.identity.username];
            let admin = bundle
                .organization
                .admins
                .contains(&entry.identity.username);
            if admin {
                parent.push(Tuple {
                    user,
                    role: Role::Admin,
                    space: org.id,
                });
            }
            if admin || !entry.teams.is_empty() {
                parent.push(Tuple {
                    user,
                    role: Role::Member,
                    space: org.id,
                });
            }
        }
        self.grant_spaces(&mut tx, bundle, &actor, &parent, report)
            .await?;
        for name in bundle.teams() {
            let team = match db::named_space(&mut *tx, Some(org.id), name).await? {
                Some(team) => team,
                None => {
                    let id = Uuid::new_v4();
                    let team = Space {
                        id,
                        name: name.into(),
                        kind: SpaceKind::Team,
                        parent_id: Some(org.id),
                        personal_owner: None,
                        path: vec![org.id, id],
                    };
                    db::insert_space(&mut tx, &team).await?;
                    team
                }
            };
            let grants: Vec<_> = bundle
                .users
                .iter()
                .flat_map(|entry| {
                    let user = subjects[&entry.identity.username].as_str();
                    entry
                        .teams
                        .get(name)
                        .into_iter()
                        .flatten()
                        .map(move |role| Tuple {
                            user,
                            role: *role,
                            space: team.id,
                        })
                })
                .collect();
            self.grant_spaces(&mut tx, bundle, &actor, &grants, report)
                .await?;
        }
        for entry in &bundle.users {
            for role in &entry.platform {
                self.authorize(&mut tx, bundle).await?;
                let user = &subjects[&entry.identity.username];
                ensure!(
                    self.directory.exists(user).await?,
                    "identity disappeared before platform grant"
                );
                self.fga.write_platform(user, *role, true).await?;
                report.grants_acknowledged += 1;
                logging::audit_relation(Some(&actor), user, role.relation(), "platform:root", true);
            }
        }
        tx.commit().await?;
        report.spaces_reconciled = 1 + bundle.teams().len();
        Ok(())
    }

    async fn grant_spaces(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        bundle: &Bundle,
        actor: &str,
        tuples: &[Tuple<'_>],
        report: &mut Report,
    ) -> Result<()> {
        // 100 is OpenFGA's default write transaction limit. The organization lock stays
        // held across batches, so parent revocations cannot interleave with child grants.
        for batch in tuples.chunks(100) {
            self.authorize(tx, bundle).await?;
            self.fga.write(batch, &[]).await?;
            report.grants_acknowledged += batch.len();
            for tuple in batch {
                logging::audit_relation(
                    Some(actor),
                    tuple.user,
                    tuple.role.as_str(),
                    &format!("space:{}", tuple.space),
                    true,
                );
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn input() -> serde_json::Value {
        json!({"organization":{"name":"TSN","admins":["alice"]},"users":[{"username":"alice","teams":["BID","fallback"],"team_roles":{"team_admin":["BID"],"team_analyst":["BID"]},"platform_roles":["admin","platform_admin","observer","platform_observer","team_manager","feature_manager","prompt_editor"]}]})
    }
    #[test]
    fn all_roles_aliases_cumulative_grants_and_per_entry_fallback() {
        let bundle = Bundle::parse(&serde_json::to_vec(&input()).unwrap()).unwrap();
        let user = &bundle.users[0];
        assert_eq!(user.platform.len(), 5);
        assert_eq!(user.teams["BID"], vec![Role::Admin, Role::Analyst]);
        assert_eq!(user.teams["fallback"], vec![Role::Member]);
    }
    #[test]
    fn duplicate_raw_role_keys_are_rejected() {
        assert!(Bundle::parse(br#"{"organization":{"name":"O","admins":["u"]},"users":[{"username":"u","team_roles":{"team_member":["A"],"team_member":["B"]}}]}"#).is_err());
    }

    // Proves: I11
    #[test]
    fn malformed_declarations_never_echo_payloads() {
        let mut cases = vec![
            json!({"private-password": true}),
            json!({"organization":{"name":"","admins":[]},"users":[]}),
        ];
        for field in [
            "username",
            "teams",
            "team_roles",
            "platform_roles",
            "password",
        ] {
            let mut value = input();
            value["users"][0][field] = json!({"private-password":true});
            cases.push(value);
        }
        let mut duplicate = input();
        let user = duplicate["users"][0].clone();
        duplicate["users"].as_array_mut().unwrap().push(user);
        cases.push(duplicate);
        for field in ["platform_roles", "teams"] {
            let mut value = input();
            value["users"][0][field] = json!([""]);
            cases.push(value);
        }
        for role in ["pending_team_admin", "suspended", "private-password"] {
            let mut value = input();
            value["users"][0]["team_roles"] = json!({role:["BID"]});
            cases.push(value);
        }
        let mut unknown = input();
        unknown["users"][0]["private-password"] = json!(true);
        cases.push(unknown);
        let mut missing = input();
        missing["organization"]["admins"] = json!(["missing"]);
        cases.push(missing);
        for value in cases {
            let error = Bundle::parse(&serde_json::to_vec(&value).unwrap())
                .err()
                .expect("must reject");
            assert!(!format!("{error:?}").contains("private-password"));
        }
        assert!(Bundle::parse(br#"{"password":"private-password", broken"#).is_err());
    }
}
