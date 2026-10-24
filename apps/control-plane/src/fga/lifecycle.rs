// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Bounded lifecycle reads. Mutation drains first pages, never a stale cursor.
use super::*;

pub(crate) struct References {
    pub keys: Vec<Value>,
    pub incoming: Vec<(Uuid, bool)>,
}
impl Fga {
    async fn page(&self, filter: Value, token: &str) -> Result<(Vec<StoredKey>, String)> {
        let reply = self.post(&format!("/stores/{}/read", self.store), json!({"tuple_key":filter, "page_size":96, "continuation_token":token, "consistency":"HIGHER_CONSISTENCY"})).await?;
        let tuples = reply["tuples"].as_array().context("missing tuples")?;
        let keys = tuples
            .iter()
            .map(|t| serde_json::from_value(t["key"].clone()))
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let token = reply["continuation_token"]
            .as_str()
            .unwrap_or("")
            .to_owned();
        Ok((keys, token))
    }
    pub(crate) async fn linked_page(
        &self,
        parent: Uuid,
        personal: bool,
        token: &str,
    ) -> Result<(Vec<Uuid>, String)> {
        let (keys, token) = self.page(json!({"object":"space:","user":format!("space:{parent}"),"relation":if personal {"organization"} else {"parent"}}), token).await?;
        Ok((
            keys.iter()
                .map(|k| space_id(&k.object))
                .collect::<Result<_>>()?,
            token,
        ))
    }
    pub(crate) async fn references(&self, id: Uuid) -> Result<References> {
        let subject = format!("space:{id}");
        let (mut keys, _) = self.page(json!({"object":subject}), "").await?;
        let mut incoming = Vec::new();
        for kind in subject_types()? {
            let (found, _) = self
                .page(json!({"object":format!("{kind}:"), "user":subject}), "")
                .await?;
            for key in found {
                if kind == "agent_template" {
                    if key.relation == "organization" {
                        // Keep the anchor until the object's remaining pages are drained.
                        let (mut grants, continuation) =
                            self.page(json!({"object":key.object}), "").await?;
                        grants.retain(|grant| grant.relation != "organization");
                        keys.extend(grants);
                        if continuation.is_empty() {
                            keys.push(key);
                        }
                    } else {
                        keys.push(key);
                    }
                    continue;
                }
                let personal = match key.relation.as_str() {
                    "parent" => false,
                    "organization" => true,
                    _ => anyhow::bail!("unsupported incoming space relation"),
                };
                incoming.push((space_id(&key.object)?, personal));
                if !keys.iter().any(|k| {
                    k.user == key.user && k.object == key.object && k.relation == key.relation
                }) {
                    keys.push(key);
                }
            }
        }
        let mut seen = std::collections::HashSet::new();
        keys.retain(|key| {
            seen.insert((key.user.clone(), key.relation.clone(), key.object.clone()))
        });
        Ok(References {
            keys: keys
                .into_iter()
                .take(96)
                .map(|k| json!({"user":k.user,"relation":k.relation,"object":k.object}))
                .collect(),
            incoming,
        })
    }
    /// An orphan has exactly one placement. Do not exhaust malformed link pages
    /// under lifecycle locks: any second key or continuation already rejects it.
    pub(crate) async fn orphan_link_matches(
        &self,
        child: Uuid,
        parent: Uuid,
        personal: bool,
    ) -> Result<bool> {
        let expected = if personal { "organization" } else { "parent" };
        for relation in ["parent", "organization"] {
            let (keys, token) = self
                .page(
                    json!({"object":format!("space:{child}"), "relation":relation}),
                    "",
                )
                .await?;
            if !token.is_empty()
                || if relation == expected {
                    keys.len() != 1 || keys[0].user != format!("space:{parent}")
                } else {
                    !keys.is_empty()
                }
            {
                return Ok(false);
            }
        }
        Ok(true)
    }
    pub(crate) async fn delete_references(
        &self,
        guard: &mut Guard,
        keys: Vec<Value>,
    ) -> Result<()> {
        self.write_guarded(guard, vec![], keys).await
    }
    pub(crate) async fn organization_guard_present(&self, id: Uuid) -> Result<bool> {
        Ok(!self
            .read_keys(json!({"object":Scope::Organization(id).object()}))
            .await?
            .is_empty())
    }
    pub(crate) async fn finish_organization_guard(
        &self,
        guard: &mut Guard,
        id: Uuid,
    ) -> Result<()> {
        let keys = self
            .read_keys(json!({"object":Scope::Organization(id).object()}))
            .await?;
        anyhow::ensure!(keys.len() == 2, "missing or corrupt organization guard");
        self.write_guarded(
            guard,
            vec![],
            keys.into_iter()
                .map(|k| json!({"user":k.user,"relation":k.relation,"object":k.object}))
                .collect(),
        )
        .await
    }
}
fn subject_types() -> Result<Vec<String>> {
    let model: Value = serde_json::from_str(include_str!("../../openfga/model.json"))?;
    let mut types = Vec::new();
    for definition in model["type_definitions"]
        .as_array()
        .context("model definitions missing")?
    {
        if definition["metadata"]["relations"]
            .as_object()
            .into_iter()
            .flat_map(|m| m.values())
            .any(|relation| {
                relation["directly_related_user_types"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .any(|t| t["type"] == "space")
            })
        {
            types.push(
                definition["type"]
                    .as_str()
                    .context("model type missing")?
                    .to_owned(),
            );
        }
    }
    Ok(types)
}
#[cfg(test)]
mod tests {
    #[test]
    fn model_space_subjects_include_template_cleanup() {
        assert_eq!(super::subject_types().unwrap(), ["space", "agent_template"]);
    }
}
