//! Store publication. Startup binds the published store and model, or publishes a fresh
//! store for an empty installation. Model replacement is an explicit operator action.
use super::*;
use crate::bootstrap;
use sqlx::PgPool;

impl Fga {
    /// Replace the pinned model after an operator has reviewed tuple compatibility and
    /// stopped every consumer. This lock serializes publication, not running consumers.
    pub async fn publish_model(self, pool: &PgPool, expected_model: &str) -> Result<Self> {
        let mut tx = bootstrap::locked(pool).await?;
        let (configured, active, previous) = binding(&mut *tx)
            .await?
            .context("initialize control-plane authorization with serve before publication")?;
        anyhow::ensure!(
            self.configured_store == configured,
            "configured OpenFGA store differs from published authorization store"
        );
        anyhow::ensure!(
            previous == expected_model,
            "published OpenFGA model changed; inspect the binding before publication"
        );
        let mut destination = self;
        destination.store = active;
        let reply = destination
            .get(&format!(
                "/stores/{}/authorization-models/{previous}",
                destination.store
            ))
            .await?;
        let actual = &reply["authorization_model"];
        anyhow::ensure!(actual["id"] == previous, "invalid published OpenFGA model");
        let expected: Value = serde_json::from_str(include_str!("../../openfga/model.json"))?;
        if !model_matches(actual, &expected, &previous) {
            let reply = destination
                .post(
                    &format!("/stores/{}/authorization-models", destination.store),
                    expected,
                )
                .await?;
            let model = reply["authorization_model_id"]
                .as_str()
                .context("missing published model id")?;
            destination = destination
                .clone()
                .bind((configured, destination.store.clone(), model.into()))
                .await?;
            sqlx::query("update authorization_store set model_id = $1 where singleton")
                .bind(model)
                .execute(&mut *tx)
                .await?;
        } else {
            destination.model = Some(previous.clone());
        }
        tx.commit().await?;
        tracing::info!(store_id=destination.store, previous_model_id=previous, model_id=?destination.model, "[REBAC] Authorization model published; restart all consumers");
        Ok(destination)
    }

    /// Bind an existing publication, or initialize only an entirely empty installation.
    pub async fn initialize(self, pool: &PgPool) -> Result<Self> {
        let mut tx = bootstrap::locked(pool).await?;
        if let Some(binding) = binding(&mut *tx).await? {
            let bound = self.bind(binding).await?;
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
                json!({"name":format!("control-plane-{}", Uuid::new_v4())}),
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
            .context("initialize control-plane authorization with serve before import")?;
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
            model_matches(actual, &expected, &model),
            "published OpenFGA model is incompatible; stop all consumers, review tuple compatibility, then run control-plane publish-authorization-model --expected-model {model}"
        );
        self.model = Some(model);
        Ok(self)
    }
}

fn model_matches(actual: &Value, expected: &Value, model: &str) -> bool {
    actual["id"] == model
        && actual["schema_version"] == expected["schema_version"]
        && normalized_model(actual["type_definitions"].clone())
            == normalized_model(expected["type_definitions"].clone())
        && actual
            .get("conditions")
            .is_none_or(|c| c.is_null() || c.as_object().is_some_and(|m| m.is_empty()))
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
