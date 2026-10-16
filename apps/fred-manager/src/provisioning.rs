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
    domain::{Role, Space, SpaceKind, SpaceRow},
    fga::{Fga, Guard, Link, Scope, Tuple},
    keycloak::Directory,
    logging, platform, spaces,
};
use anyhow::{Result, ensure};
use serde::Serialize;
use sqlx::{PgPool, Postgres, Transaction};
use std::collections::{BTreeMap, btree_map};
use uuid::Uuid;

pub use crate::blueprint::Bundle;
use crate::error::AppError;

#[derive(Debug, thiserror::Error)]
#[error("invalid or expired operator bearer")]
struct Unauthorized;

#[derive(Debug, thiserror::Error)]
#[error("{message}")]
pub struct Failure {
    pub status: axum::http::StatusCode,
    message: String,
}
impl Failure {
    fn at(phase: &str, error: anyhow::Error, report: &Report) -> Self {
        use axum::http::StatusCode as S;
        let status = if error.is::<crate::fga::Conflict>() {
            S::CONFLICT
        } else if let Some(e) = error.downcast_ref::<AppError>() {
            match e {
                AppError::Forbidden | AppError::Denied(_) => S::FORBIDDEN,
                AppError::BadRequest(_) | AppError::Unprocessable(_) => S::UNPROCESSABLE_ENTITY,
                AppError::Conflict(_) | AppError::NotFound => S::CONFLICT,
                AppError::Unavailable(_) => S::SERVICE_UNAVAILABLE,
                AppError::Internal(_) => S::SERVICE_UNAVAILABLE,
            }
        } else if error.is::<Unauthorized>() {
            S::UNAUTHORIZED
        } else if let Some(e) = error.downcast_ref::<sqlx::Error>() {
            match e {
                sqlx::Error::Database(db)
                    if db.is_unique_violation() || db.is_foreign_key_violation() =>
                {
                    S::CONFLICT
                }
                sqlx::Error::Io(_)
                | sqlx::Error::Tls(_)
                | sqlx::Error::PoolTimedOut
                | sqlx::Error::PoolClosed => S::SERVICE_UNAVAILABLE,
                _ => S::INTERNAL_SERVER_ERROR,
            }
        } else {
            S::SERVICE_UNAVAILABLE
        };
        // Never retain the dependency error chain or interpolate supplied values.
        let reason = match status {
            S::FORBIDDEN => "forbidden",
            S::UNAUTHORIZED => "invalid or expired operator bearer",
            S::UNPROCESSABLE_ENTITY => "invalid identity or space declaration",
            S::CONFLICT => "state or authorization conflict",
            S::INTERNAL_SERVER_ERROR => "internal failure",
            _ => "dependency unavailable",
        };
        Self {
            status,
            message: format!(
                "provisioning {phase} failed: {reason}; {report}; correct the cause and replay (acknowledgments may be incomplete)"
            ),
        }
    }
}
fn invalid(message: &str) -> anyhow::Error {
    AppError::Unprocessable(message.into()).into()
}
fn conflict(message: &str) -> anyhow::Error {
    AppError::Conflict(message.into()).into()
}

#[derive(Debug, Default, Serialize, utoipa::ToSchema)]
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
    async fn authorize(&self) -> Result<String> {
        ensure!(
            self.auth.directory_subjects_match(self.directory.realm()),
            "import requires enabled Keycloak subject authentication in the directory realm"
        );
        let caller = self
            .auth
            .authenticate(Some(self.bearer))
            .await
            .map_err(|_| Unauthorized)?;
        platform::require_owner(self.fga, &caller.uid).await?;
        Ok(caller.uid)
    }

    /// All predictable conflicts are checked for the whole bundle before writes.
    /// Directory traversal does not hold mutation locks; reconciliation rereads state.
    async fn preflight(&self, bundle: &Bundle) -> Result<()> {
        self.authorize().await?;
        let mut subjects = BTreeMap::new();
        let mut emails = std::collections::BTreeSet::new();
        for entry in &bundle.users {
            let user = &entry.identity;
            match self.directory.find_username(&user.username).await? {
                Some(found) => {
                    subjects.insert(user.username.clone(), found.id);
                }
                None if !user.password.as_ref().is_some_and(|p| !p.is_empty()) => {
                    return Err(invalid("missing identity requires a password"));
                }
                None => {
                    let email =
                        crate::keycloak::effective_email(&user.username, user.email.as_deref());
                    if !emails.insert(email.to_lowercase())
                        || self.directory.email_in_use(&email).await?
                    {
                        return Err(conflict("new identity email is already in use"));
                    }
                }
            }
        }
        let mut tx = bootstrap::locked(self.pool).await?;
        self.authorize().await?;
        let resolved = self.resolve_spaces(&mut tx, bundle).await?;
        self.validate_parents(bundle, &resolved, &subjects, None)
            .await?;
        tx.rollback().await?;
        Ok(())
    }

    /// Resolve organization names under the platform lock, then lock every organization
    /// in UUID order and resolve children among their parent's OpenFGA children. The
    /// returned IDs are candidates until the enclosing SQL commit.
    async fn resolve_spaces(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        bundle: &Bundle,
    ) -> Result<Vec<(Space, bool)>> {
        let mut resolved: Vec<(Space, bool)> = Vec::new();
        let mut children: BTreeMap<Uuid, Vec<SpaceRow>> = BTreeMap::new();
        for organizations in [true, false] {
            for declaration in bundle
                .spaces
                .iter()
                .filter(|s| (s.kind == SpaceKind::Organization) == organizations)
            {
                let parent = declaration.parent.map(|p| &resolved[p].0);
                let parent_new = declaration.parent.is_some_and(|p| resolved[p].1);
                let existing = match parent {
                    _ if parent_new => None,
                    None => db::organization_named(&mut **tx, &declaration.name).await?,
                    Some(parent) => {
                        if let btree_map::Entry::Vacant(slot) = children.entry(parent.id) {
                            let ids = self.fga.linked_to(parent.id, false).await?;
                            slot.insert(db::spaces(&mut **tx, &ids).await?);
                        }
                        children[&parent.id]
                            .iter()
                            .find(|c| c.name == declaration.name)
                            .cloned()
                    }
                };
                let is_new = existing.is_none();
                let row = if let Some(existing) = existing {
                    if existing.kind != declaration.kind {
                        return Err(conflict("incompatible space collision"));
                    }
                    existing
                } else {
                    if !declaration.roles.values().any(|r| r.contains(&Role::Admin)) {
                        return Err(invalid("new space requires a declared admin"));
                    }
                    if declaration.kind == SpaceKind::Organization
                        && !declaration.roles.values().any(|r| r.contains(&Role::Owner))
                    {
                        return Err(invalid("new organization requires a declared owner"));
                    }
                    SpaceRow {
                        id: Uuid::new_v4(),
                        name: declaration.name.clone(),
                        kind: declaration.kind,
                        personal_owner: None,
                    }
                };
                let space = Space::placed(row, parent.map_or(&[], |p| &p.path), None);
                resolved.push((space, is_new));
            }
            if !organizations {
                break;
            }
            let mut organizations: Vec<_> = resolved
                .iter()
                .filter(|(s, _)| s.kind == SpaceKind::Organization)
                .map(|(s, _)| s)
                .collect();
            organizations.sort_by_key(|s| s.id);
            for org in organizations {
                spaces::lock_organization(tx, org).await?;
            }
        }
        Ok(resolved)
    }

    async fn validate_parents(
        &self,
        bundle: &Bundle,
        resolved: &[(Space, bool)],
        subjects: &BTreeMap<String, String>,
        organization: Option<Uuid>,
    ) -> Result<()> {
        for (i, child) in bundle.spaces.iter().enumerate() {
            if organization.is_some_and(|o| resolved[i].0.organization != o) {
                continue;
            }
            let Some(p) = child.parent else {
                continue;
            };
            for (username, roles) in &child.roles {
                if roles.is_empty() {
                    continue;
                }
                // Declared or existing, the parent role must be direct: inherited access
                // does not satisfy the parent/child invariant.
                if bundle.spaces[p]
                    .roles
                    .get(username)
                    .is_some_and(|r| r.iter().any(|r| r.grants_content()))
                {
                    continue;
                }
                let allowed =
                    if let Some(subject) = subjects.get(username).filter(|_| !resolved[p].1) {
                        self.fga
                            .direct_roles_on(subject, resolved[p].0.id)
                            .await?
                            .iter()
                            .any(|r| r.grants_content())
                    } else {
                        false
                    };
                if !allowed {
                    return Err(invalid("child role requires parent content membership"));
                }
            }
        }
        Ok(())
    }

    pub async fn run(&self, bundle: &Bundle) -> Result<Report> {
        let mut report = Report::default();
        // Error causes from SQL may contain user-supplied values. Return only safe phase
        // and counters; upstream bodies and bundle values never enter the error chain.
        self.preflight(bundle)
            .await
            .map_err(|e| Failure::at("preflight", e, &report))?;
        let mut subjects = BTreeMap::new();
        for entry in &bundle.users {
            let result = async {
                let tx = bootstrap::locked(self.pool).await?;
                let mut guard = self.fga.guard(&[Scope::Platform]).await?;
                self.authorize().await?;
                // Authorize external dispatch; a timeout is not remote rollback.
                self.fga.fence(&mut guard).await?;
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
            result.map_err(|e| Failure::at("identities", e, &report))?;
        }
        self.reconcile(bundle, &subjects, &mut report)
            .await
            .map_err(|e| Failure::at("roles/spaces", e, &report))?;
        Ok(report)
    }

    async fn reconcile(
        &self,
        bundle: &Bundle,
        subjects: &BTreeMap<String, String>,
        report: &mut Report,
    ) -> Result<()> {
        let mut tx = bootstrap::locked(self.pool).await?;
        self.authorize().await?;
        let resolved = self.resolve_spaces(&mut tx, bundle).await?;
        // Whole-bundle checks precede publication; each subtree is checked again
        // after capturing its guard, so a late revoke cannot invalidate the decision.
        self.validate_parents(bundle, &resolved, subjects, None)
            .await?;
        // Verify every owner before publishing any subtree. External IAM deletion is
        // not transactional with OpenFGA; this is an existence check, not an account lease.
        let owners: std::collections::BTreeSet<_> = bundle
            .spaces
            .iter()
            .flat_map(|s| &s.roles)
            .filter(|(_, roles)| roles.contains(&Role::Owner))
            .map(|(username, _)| subjects[username].clone())
            .collect();
        let owners: Vec<_> = owners.into_iter().collect();
        for batch in owners.chunks(8) {
            let mut checks = tokio::task::JoinSet::new();
            for subject in batch {
                let directory = self.directory.clone();
                let subject = subject.clone();
                checks.spawn(async move { directory.exists(&subject).await });
            }
            while let Some(result) = checks.join_next().await {
                ensure!(result??, "identity disappeared before owner grant");
            }
        }
        for (org, is_new) in resolved
            .iter()
            .filter(|(s, _)| s.kind == SpaceKind::Organization)
        {
            if *is_new {
                self.fga
                    .initialize_guard(Scope::Organization(org.id))
                    .await?;
            }
            let mut guard = self
                .fga
                .guard(&[Scope::Platform, Scope::Organization(org.id)])
                .await?;
            let actor = self.authorize().await?;
            self.validate_parents(bundle, &resolved, subjects, Some(org.id))
                .await?;
            let mut wrote = false;
            for (declaration, (space, is_new)) in bundle
                .spaces
                .iter()
                .zip(&resolved)
                .filter(|(_, (s, _))| s.organization == org.id)
            {
                let mut link = None;
                if *is_new {
                    db::insert_space(&mut tx, space).await?;
                    link = space.parent_id.map(|parent| Link::Parent {
                        child: space.id,
                        parent,
                    });
                }
                let grants: Vec<_> = declaration
                    .roles
                    .iter()
                    .flat_map(|(username, roles)| {
                        let user = subjects[username].as_str();
                        roles.iter().map(move |role| Tuple {
                            user,
                            role: *role,
                            space: space.id,
                        })
                    })
                    .collect();
                wrote |= link.is_some() || !grants.is_empty();
                self.grant_spaces(&mut guard, &actor, link, &grants, report)
                    .await?;
            }
            if !wrote {
                self.fga.fence(&mut guard).await?;
            }
        }
        if bundle.users.iter().any(|e| !e.platform.is_empty()) {
            let mut guard = self.fga.guard(&[Scope::Platform]).await?;
            for entry in &bundle.users {
                for role in &entry.platform {
                    let actor = self.authorize().await?;
                    let user = &subjects[&entry.identity.username];
                    ensure!(
                        self.directory.exists(user).await?,
                        "identity disappeared before platform grant"
                    );
                    self.fga
                        .write_platform(&mut guard, user, *role, true)
                        .await?;
                    report.grants_acknowledged += 1;
                    logging::audit_relation(
                        Some(&actor),
                        user,
                        role.relation(),
                        "platform:root",
                        true,
                    );
                }
            }
        }
        tx.commit().await?;
        report.spaces_reconciled = resolved.len();
        Ok(())
    }

    async fn grant_spaces(
        &self,
        guard: &mut Guard,
        actor: &str,
        mut link: Option<Link>,
        tuples: &[Tuple<'_>],
        report: &mut Report,
    ) -> Result<()> {
        // Two scopes consume four operations in OpenFGA's 100-operation transaction.
        // A new space's link shares its first batch. Acknowledged revisions carry
        // forward; any failed batch invalidates the attempt.
        let mut rest = tuples;
        while link.is_some() || !rest.is_empty() {
            let room = 96 - usize::from(link.is_some());
            let (batch, tail) = rest.split_at(room.min(rest.len()));
            rest = tail;
            self.authorize().await?;
            let links: Vec<Link> = link.take().into_iter().collect();
            self.fga.write_created(guard, &links, batch).await?;
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
