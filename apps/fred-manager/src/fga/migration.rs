//! One-time, offline cutover. Each unpublished attempt uses a fresh store so a late
//! legacy write or failed copy cannot alter the active authorization state.
use super::*;
use crate::{
    bootstrap,
    domain::{self, Space, SpaceKind},
};
use sqlx::PgPool;

impl Fga {
    /// Bind an existing publication, or initialize only an entirely empty installation.
    /// `migrate_existing` is reserved for the explicit offline operator command: callers
    /// must stop legacy writers and settle pending writes before capturing the source.
    pub async fn initialize(self, pool: &PgPool, migrate_existing: bool) -> Result<Self> {
        let mut tx = bootstrap::locked(pool).await?;
        if let Some(binding) = binding(&mut *tx).await? {
            return self.bind(binding).await;
        }
        anyhow::ensure!(
            !self.ambiguous_source,
            "multiple legacy stores match configuration; resolve before migration"
        );
        let spaces: Vec<Space> = sqlx::query_as(
            "select id, kind, name, parent_id, personal_owner, path from space order by path",
        )
        .fetch_all(&mut *tx)
        .await?;
        let keys = self.read_keys(json!({})).await?;
        let bootstrap = bootstrap::marker(&mut tx).await?;
        anyhow::ensure!(
            migrate_existing || (spaces.is_empty() && keys.is_empty() && bootstrap.is_none()),
            "existing authorization requires offline migrate-authorization; stop legacy writers and settle pending writes first"
        );
        validate(&spaces, &keys)?;
        if !keys.is_empty() {
            let reply = self
                .get(&format!(
                    "/stores/{}/authorization-models?page_size=1",
                    self.store
                ))
                .await?;
            let actual = reply["authorization_models"]
                .as_array()
                .and_then(|m| m.first())
                .context("legacy authorization model is missing")?;
            let expected: Value = serde_json::from_str(include_str!("../../openfga/model.json"))?;
            let mut legacy = expected.clone();
            legacy["type_definitions"]
                .as_array_mut()
                .unwrap()
                .retain(|t| t["type"] != "guard" && t["type"] != "revision");
            let definitions = normalized_model(actual["type_definitions"].clone());
            anyhow::ensure!(
                actual["schema_version"] == expected["schema_version"]
                    && (definitions == normalized_model(expected["type_definitions"].clone())
                        || definitions == normalized_model(legacy["type_definitions"].clone()))
                    && actual
                        .get("conditions")
                        .is_none_or(|c| c.is_null() || c.as_object().is_some_and(|m| m.is_empty())),
                "legacy authorization model changes permission semantics; repair before migration"
            );
        }
        let source_store = self.store.clone();
        let mut destination = self.clone();
        let created = self
            .post(
                "/stores",
                json!({"name":format!("fred-manager-{}", Uuid::new_v4())}),
            )
            .await?;
        destination.store = created["id"]
            .as_str()
            .context("missing destination store id")?
            .into();
        let model = destination
            .post(
                &format!("/stores/{}/authorization-models", destination.store),
                serde_json::from_str(include_str!("../../openfga/model.json"))?,
            )
            .await?;
        destination.model = Some(
            model["authorization_model_id"]
                .as_str()
                .context("missing destination model id")?
                .into(),
        );
        for batch in keys.chunks(100) {
            destination
                .post(
                    &format!("/stores/{}/write", destination.store),
                    json!({
                        "authorization_model_id":destination.model,
                        "writes":{"tuple_keys":batch,"on_duplicate":"error"}
                    }),
                )
                .await?;
        }
        // OpenFGA evaluates parent content access using the pinned model; Rust does
        // not introduce a second permission evaluator during cutover.
        let parents: std::collections::BTreeMap<_, _> =
            spaces.iter().map(|s| (s.id, s.parent_id)).collect();
        let mut checked = std::collections::BTreeSet::new();
        for key in &keys {
            if let Some(id) = key.object.strip_prefix("space:") {
                let id: Uuid = id.parse()?;
                if let Some(parent) = parents[&id] {
                    let user = key.user.strip_prefix("user:").unwrap();
                    if checked.insert((parent, user)) {
                        anyhow::ensure!(
                            destination.check(user, Permission::Read, parent).await?,
                            "legacy child grant lacks parent content membership; repair before migration"
                        );
                    }
                }
            }
        }
        destination.initialize_guard(Scope::Platform).await?;
        for space in &spaces {
            if space.kind == SpaceKind::Organization {
                destination
                    .initialize_guard(Scope::Organization(space.id))
                    .await?;
            }
        }
        sqlx::query("insert into authorization_store (configured_store, source_store, active_store, model_id) values ($1,$2,$3,$4)")
            .bind(&self.configured_store)
            .bind(source_store).bind(&destination.store).bind(&destination.model)
            .execute(&mut *tx).await?;
        tx.commit().await?;
        tracing::info!(store_id=destination.store, model_id=?destination.model, tuples=keys.len(), spaces=spaces.len(), "[REBAC] Authorization store published");
        Ok(destination)
    }

    /// Import and ordinary connections load only a published binding. No fallback and
    /// no model synchronization: a lost/corrupt publication is an operator error.
    pub async fn load(self, pool: &PgPool) -> Result<Self> {
        let binding = binding(pool)
            .await?
            .context("initialize fred-manager authorization with serve before import")?;
        self.bind(binding).await
    }

    async fn bind(mut self, (source, active, model): (String, String, String)) -> Result<Self> {
        anyhow::ensure!(
            self.configured_store == source,
            "configured OpenFGA store differs from published authorization store"
        );
        self.store = active;
        let reply = self
            .get(&format!(
                "/stores/{}/authorization-models/{model}",
                self.store
            ))
            .await?;
        let actual = &reply["authorization_model"];
        let expected: Value = serde_json::from_str(include_str!("../../openfga/model.json"))?;
        anyhow::ensure!(
            actual["id"] == model
                && actual["schema_version"] == expected["schema_version"]
                && normalized_model(actual["type_definitions"].clone())
                    == normalized_model(expected["type_definitions"].clone())
                && actual
                    .get("conditions")
                    .is_none_or(|c| c.is_null() || c.as_object().is_some_and(|m| m.is_empty())),
            "published OpenFGA model is incompatible"
        );
        self.model = Some(model);
        Ok(self)
    }
}

async fn binding<'e>(
    executor: impl sqlx::PgExecutor<'e>,
) -> Result<Option<(String, String, String)>> {
    Ok(sqlx::query_as(
        "select configured_store, active_store, model_id from authorization_store where singleton",
    )
    .fetch_optional(executor)
    .await?)
}

/// Validate raw tuples, never the filtered public readers. Unsupported data is an
/// explicit repair requirement; migration must not silently discard it.
fn validate(spaces: &[Space], keys: &[StoredKey]) -> Result<()> {
    use std::collections::{BTreeMap, BTreeSet};
    let by_id: BTreeMap<_, _> = spaces.iter().map(|s| (s.id, s)).collect();
    for space in spaces {
        let parent = space
            .parent_id
            .map(|id| by_id.get(&id).copied().context("legacy parent is absent"))
            .transpose()?;
        domain::check_parent(space.kind, parent)?;
        anyhow::ensure!(
            space.path == domain::space_path(parent, space.id),
            "legacy space path disagrees with hierarchy; repair before migration"
        );
    }
    let mut admins = BTreeSet::new();
    for key in keys {
        anyhow::ensure!(
            key.condition.as_ref().is_none_or(|c| c.is_null()),
            "legacy conditional grant requires repair"
        );
        let user = key
            .user
            .strip_prefix("user:")
            .context("legacy grant has unsupported subject")?;
        anyhow::ensure!(
            !user.is_empty() && !user.contains(['#', '*']),
            "legacy grant has unsupported subject"
        );
        if key.object == PLATFORM {
            anyhow::ensure!(
                PlatformRole::parse(&key.relation).is_some(),
                "legacy platform relation requires repair"
            );
        } else {
            let id: Uuid = key
                .object
                .strip_prefix("space:")
                .context("legacy object requires repair")?
                .parse()?;
            let space = by_id
                .get(&id)
                .context("legacy grant references absent space; repair before migration")?;
            let role =
                Role::parse(&key.relation).context("legacy space relation requires repair")?;
            if let Some(owner) = &space.personal_owner {
                anyhow::ensure!(
                    owner == user && matches!(role, Role::Member | Role::Editor),
                    "legacy personal-space grant requires repair"
                );
            }
            if role == Role::Admin {
                admins.insert(id);
            }
        }
    }
    for space in spaces {
        anyhow::ensure!(
            space.personal_owner.is_some() || admins.contains(&space.id),
            "legacy non-personal space has no administrator; repair before migration"
        );
    }
    Ok(())
}
