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

//! Domain types and the placement rules. Pure functions: no I/O, unit-tested.

use serde::{Deserialize, Serialize};
use unicode_normalization::UnicodeNormalization;
use uuid::Uuid;

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema,
)]
#[sqlx(type_name = "space_kind", rename_all = "lowercase")]
#[serde(rename_all = "lowercase")]
pub enum SpaceKind {
    Organization,
    Team,
    Project,
    Personal,
}

/// Space and folder names are stored, compared and kept unique in this form: NFC,
/// without surrounding whitespace, nonblank, at most `max` characters, no controls.
pub(crate) fn canonical_name(raw: &str, max: usize) -> Option<String> {
    let nfc: String = raw.nfc().collect();
    let name = nfc.trim();
    (!name.is_empty() && name.chars().count() <= max && !name.chars().any(char::is_control))
        .then(|| name.to_owned())
}

/// An identity usable as an OpenFGA `user:<id>`: no whitespace, `:` or `#`.
pub(crate) fn valid_subject(subject: &str) -> bool {
    (1..=255).contains(&subject.chars().count())
        && !subject
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == ':' || c == '#')
}

/// Space labels keep inner spaces and slashes; they are not paths.
pub(crate) fn space_name(raw: &str) -> Option<String> {
    canonical_name(raw, 180)
}

/// Immutable placement is recorded with the space; roles remain in OpenFGA.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct SpaceRow {
    pub id: Uuid,
    pub kind: SpaceKind,
    pub name: String,
    pub personal_owner: Option<String>,
    pub parent_id: Option<Uuid>,
    pub organization_id: Uuid,
}

/// A space with its immutable placement and derived search path.
#[derive(Debug, Clone, Serialize, utoipa::ToSchema)]
pub struct Space {
    pub id: Uuid,
    pub kind: SpaceKind,
    pub name: String,
    #[schema(required = true)]
    pub parent_id: Option<Uuid>,
    #[schema(required = true)]
    pub personal_owner: Option<String>,
    /// Ancestors then self: the search scope. A personal space's path is itself.
    pub path: Vec<Uuid>,
    /// The organization whose lock serializes this space's mutations.
    #[serde(skip)]
    pub organization: Uuid,
}

impl From<SpaceRow> for Space {
    fn from(row: SpaceRow) -> Self {
        let mut path = Vec::new();
        if let Some(parent) = row.parent_id {
            if parent != row.organization_id {
                path.push(row.organization_id);
            }
            path.push(parent);
        }
        path.push(row.id);
        Space {
            organization: row.organization_id,
            parent_id: row.parent_id,
            path,
            id: row.id,
            kind: row.kind,
            name: row.name,
            personal_owner: row.personal_owner,
        }
    }
}

#[derive(Debug, Clone, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct Folder {
    pub id: Uuid,
    pub space_id: Uuid,
    #[schema(required = true)]
    pub parent_id: Option<Uuid>,
    pub name: String,
    pub path: String,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, Clone, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct Document {
    pub retrievable: bool,
    pub retrievable_pending: bool,
    pub id: Uuid,
    pub space_id: Uuid,
    #[schema(required = true)]
    pub folder_id: Option<Uuid>,
    pub name: String,
    pub mime: String,
    pub size: i64,
    pub sha256: String,
    pub created_by: String,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

/// Direct roles stored in OpenFGA.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, utoipa::ToSchema,
)]
#[serde(rename_all = "lowercase")]
pub enum Role {
    Member,
    Editor,
    Owner,
    Analyst,
    /// Technical governance and aggregates; grants no document content access.
    #[serde(rename = "organization_admin")]
    OrganizationAdmin,
}

impl Role {
    pub fn as_str(self) -> &'static str {
        match self {
            Role::Member => "member",
            Role::Editor => "editor",
            Role::Owner => "owner",
            Role::Analyst => "analyst",
            Role::OrganizationAdmin => "organization_admin",
        }
    }

    pub fn parse(s: &str) -> Option<Role> {
        match s {
            "member" => Some(Role::Member),
            "editor" => Some(Role::Editor),
            "owner" => Some(Role::Owner),
            "analyst" => Some(Role::Analyst),
            "organization_admin" => Some(Role::OrganizationAdmin),
            _ => None,
        }
    }

    /// Owner is governance only: it grants no access to content.
    pub fn grants_content(self) -> bool {
        matches!(self, Role::Member | Role::Editor | Role::Analyst)
    }

    /// Roles the model extends to every descendant space.
    pub fn descends(self) -> bool {
        matches!(self, Role::Editor | Role::Owner | Role::Analyst)
    }
}

/// Computed permissions checked against OpenFGA.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum Permission {
    Read,
    Write,
    Manage,
}

impl Permission {
    pub fn as_str(self) -> &'static str {
        match self {
            Permission::Read => "can_read",
            Permission::Write => "can_write",
            Permission::Manage => "can_manage",
        }
    }
}

#[derive(Debug, PartialEq, Eq, thiserror::Error)]
pub enum RuleError {
    #[error("an organization has no parent")]
    NestedOrganization,
    #[error("a team must have an organization as parent")]
    TeamOutsideOrganization,
    #[error("a project must have a non-personal team as parent")]
    ProjectOutsideTeam,
    #[error("a personal space must use the dedicated creation endpoint")]
    PersonalCreationRequired,
}

/// Organization > team > project. Personal spaces use their dedicated creation path.
pub fn check_parent(kind: SpaceKind, parent: Option<&Space>) -> Result<(), RuleError> {
    match (kind, parent) {
        (SpaceKind::Organization, None) => Ok(()),
        (SpaceKind::Organization, Some(_)) => Err(RuleError::NestedOrganization),
        (SpaceKind::Team, Some(p)) if p.kind == SpaceKind::Organization => Ok(()),
        (SpaceKind::Team, _) => Err(RuleError::TeamOutsideOrganization),
        (SpaceKind::Project, Some(p)) if p.kind == SpaceKind::Team => Ok(()),
        (SpaceKind::Project, _) => Err(RuleError::ProjectOutsideTeam),
        (SpaceKind::Personal, _) => Err(RuleError::PersonalCreationRequired),
    }
}

pub fn folder_path(parent: Option<&Folder>, id: Uuid) -> String {
    let base = parent.map(|p| p.path.as_str()).unwrap_or("/");
    format!("{base}{id}/")
}

/// Removing `role` would drop the user's content access to a space while they still hold
/// a role on one of its child spaces, breaking "a role on a space needs read on its parent".
pub fn revocation_blocked(role: Role, roles_on_space: &[Role], holds_role_in_child: bool) -> bool {
    let keeps_content = roles_on_space
        .iter()
        .any(|r| *r != role && r.grants_content());
    role.grants_content() && !keeps_content && holds_role_in_child
}

#[cfg(test)]
mod tests {
    use super::*;

    fn space(kind: SpaceKind, parent: Option<&Space>, personal: bool) -> Space {
        let id = Uuid::new_v4();
        let row = SpaceRow {
            id,
            kind,
            name: "x".into(),
            personal_owner: personal.then(|| "bob".into()),
            parent_id: parent.filter(|_| !personal).map(|p| p.id),
            organization_id: parent.map_or(id, |p| p.organization),
        };
        Space::from(row)
    }

    // Proves: I1
    #[test]
    fn parent_rules() {
        let org = space(SpaceKind::Organization, None, false);
        let team = space(SpaceKind::Team, Some(&org), false);
        let personal = space(SpaceKind::Personal, Some(&org), true);
        let project = space(SpaceKind::Project, Some(&team), false);

        assert_eq!(check_parent(SpaceKind::Organization, None), Ok(()));
        assert_eq!(check_parent(SpaceKind::Team, Some(&org)), Ok(()));
        assert_eq!(check_parent(SpaceKind::Project, Some(&team)), Ok(()));

        assert!(check_parent(SpaceKind::Organization, Some(&org)).is_err());
        assert!(check_parent(SpaceKind::Personal, None).is_err());
        assert!(check_parent(SpaceKind::Personal, Some(&org)).is_err());
        assert!(check_parent(SpaceKind::Team, Some(&personal)).is_err());
        assert!(check_parent(SpaceKind::Team, None).is_err());
        assert!(check_parent(SpaceKind::Team, Some(&team)).is_err());
        assert!(check_parent(SpaceKind::Project, Some(&org)).is_err());
        assert!(check_parent(SpaceKind::Project, Some(&personal)).is_err());
        assert!(check_parent(SpaceKind::Project, Some(&project)).is_err());
    }

    // Proves: I7
    #[test]
    fn search_scope_is_ancestors_then_self() {
        let tsn = space(SpaceKind::Organization, None, false);
        let bid = space(SpaceKind::Team, Some(&tsn), false);
        let proj = space(SpaceKind::Project, Some(&bid), false);
        let alice = space(SpaceKind::Personal, Some(&tsn), true);
        assert_eq!(bid.path, vec![tsn.id, bid.id]);
        assert_eq!(proj.path, vec![tsn.id, bid.id, proj.id]);
        assert_eq!(proj.organization, tsn.id);
        assert_eq!(
            (alice.path.clone(), alice.organization),
            (vec![alice.id], tsn.id)
        );
    }

    #[test]
    fn folder_paths_nest_by_id() {
        let space_id = Uuid::new_v4();
        let ao = Folder {
            created_at: chrono::Utc::now(),
            id: Uuid::new_v4(),
            space_id,
            parent_id: None,
            name: "Appels d'offres".into(),
            path: String::new(),
        };
        let ao = Folder {
            path: folder_path(None, ao.id),
            ..ao
        };
        let y26 = Uuid::new_v4();
        let sub = folder_path(Some(&ao), y26);
        assert_eq!(ao.path, format!("/{}/", ao.id));
        assert_eq!(sub, format!("/{}/{}/", ao.id, y26));
        assert!(sub.starts_with(&ao.path));
    }

    #[test]
    fn revocation_rules() {
        use Role::*;
        assert!(revocation_blocked(Member, &[Member], true));
        assert!(!revocation_blocked(Member, &[Member], false));
        assert!(!revocation_blocked(Member, &[Member, Editor], true));
        assert!(revocation_blocked(Editor, &[Editor, Owner], true));
        assert!(!revocation_blocked(Owner, &[Owner], true));
    }
}
