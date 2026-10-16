//! Store publication. Startup binds the published store and model, or publishes a fresh
//! store for an empty installation. Exact additive model upgrades preserve tuples.
use super::*;
use crate::bootstrap;
use sqlx::PgPool;

impl Fga {
    /// Bind an existing publication, or initialize only an entirely empty installation.
    pub async fn initialize(self, pool: &PgPool) -> Result<Self> {
        let mut tx = bootstrap::locked(pool).await?;
        if let Some(binding) = binding(&mut *tx).await? {
            let bound = self.bind(binding, Some(&mut tx)).await?;
            tx.commit().await?;
            return Ok(bound);
        }
        anyhow::ensure!(
            !self.ambiguous_source,
            "multiple stores match configuration; resolve before initialization"
        );
        let spaces: i64 = sqlx::query_scalar("select count(*) from space")
            .fetch_one(&mut *tx)
            .await?;
        let keys = self.read_keys(json!({})).await?;
        let bootstrap = bootstrap::marker(&mut tx).await?;
        anyhow::ensure!(
            spaces == 0 && keys.is_empty() && bootstrap.is_none(),
            "existing manager state has no published authorization store; reset local Fred data"
        );
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
        destination.initialize_guard(Scope::Platform).await?;
        sqlx::query("insert into authorization_store (configured_store, source_store, active_store, model_id) values ($1,$2,$3,$4)")
            .bind(&self.configured_store)
            .bind(source_store).bind(&destination.store).bind(&destination.model)
            .execute(&mut *tx).await?;
        tx.commit().await?;
        tracing::info!(store_id=destination.store, model_id=?destination.model, "[REBAC] Authorization store published");
        Ok(destination)
    }

    /// Import and ordinary connections load only a published binding. No fallback and
    /// no model synchronization: a lost/corrupt publication is an operator error.
    pub async fn load(self, pool: &PgPool) -> Result<Self> {
        let binding = binding(pool)
            .await?
            .context("initialize fred-manager authorization with serve before import")?;
        self.bind(binding, None).await
    }

    async fn bind(
        mut self,
        (source, active, model): (String, String, String),
        upgrade: Option<&mut sqlx::Transaction<'_, sqlx::Postgres>>,
    ) -> Result<Self> {
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
        let matches = |expected: &Value| {
            actual["id"] == model
                && actual["schema_version"] == expected["schema_version"]
                && normalized_model(actual["type_definitions"].clone())
                    == normalized_model(expected["type_definitions"].clone())
                && actual
                    .get("conditions")
                    .is_none_or(|c| c.is_null() || c.as_object().is_some_and(|m| m.is_empty()))
        };
        if matches(&expected) {
            self.model = Some(model);
        } else {
            let previous: Value = serde_json::from_str(include_str!(
                "../../openfga/model-before-personal-eligibility.json"
            ))?;
            anyhow::ensure!(
                matches(&previous),
                "published OpenFGA model is incompatible; operator reconciliation required"
            );
            let tx = upgrade.context("published model requires initialization with sync_schema_on_init before ordinary loading")?;
            let reply = self
                .post(
                    &format!("/stores/{}/authorization-models", self.store),
                    expected,
                )
                .await?;
            let model = reply["authorization_model_id"]
                .as_str()
                .context("missing upgraded model id")?;
            sqlx::query("update authorization_store set model_id = $1 where singleton")
                .bind(model)
                .execute(&mut **tx)
                .await?;
            self.model = Some(model.to_owned());
            tracing::info!(
                store_id = self.store,
                model_id = model,
                "[REBAC] Additive authorization model published"
            );
        }
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn personal_model_is_an_exact_additive_upgrade() {
        let previous: Value = serde_json::from_str(include_str!(
            "../../openfga/model-before-personal-eligibility.json"
        ))
        .unwrap();
        let mut current: Value =
            serde_json::from_str(include_str!("../../openfga/model.json")).unwrap();
        let space = current["type_definitions"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|t| t["type"] == "space")
            .unwrap();
        for key in ["personal_space_creator", "can_create_personal_space"] {
            assert!(
                space["relations"]
                    .as_object_mut()
                    .unwrap()
                    .remove(key)
                    .is_some()
            );
            space["metadata"]["relations"]
                .as_object_mut()
                .unwrap()
                .remove(key);
        }
        assert_eq!(normalized_model(current), normalized_model(previous));
    }
}
