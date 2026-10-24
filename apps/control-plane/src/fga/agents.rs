// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization template defaults and effective team use, evaluated by OpenFGA.
use super::*;

impl Fga {
    /// Direct organization markers only; exceptions remain untouched by the switch.
    pub async fn agent_default_on(&self, organization: Uuid, template: Uuid) -> Result<bool> {
        Ok(!self
            .read_keys(json!({
                "object": format!("agent_template:{template}"),
                "user": format!("space:{organization}"), "relation": "default_on"
            }))
            .await?
            .is_empty())
    }

    /// Caller holds the organization lock and captured the guard before authorization.
    pub async fn set_agent_default_on(
        &self,
        guard: &mut Guard,
        organization: Uuid,
        template: Uuid,
        on: bool,
    ) -> Result<bool> {
        let previous = self.agent_default_on(organization, template).await?;
        let key = json!({"object":format!("agent_template:{template}"),
            "user":format!("space:{organization}"), "relation":"default_on"});
        let anchor = json!({"object":format!("agent_template:{template}"),
            "user":format!("space:{organization}"), "relation":"organization"});
        let mut writes = vec![anchor];
        let mut deletes = vec![];
        if on {
            writes.push(key);
        } else if previous {
            deletes.push(key);
        }
        self.write_guarded(guard, writes, deletes).await?;
        Ok(previous != on)
    }

    /// The trusted space placement supplies context, never caller-provided tuples.
    pub async fn can_use_agent(
        &self,
        template: Uuid,
        space: &crate::domain::Space,
    ) -> Result<bool> {
        anyhow::ensure!(
            matches!(
                space.kind,
                crate::domain::SpaceKind::Team | crate::domain::SpaceKind::Personal
            ),
            "agent use requires a team or personal space"
        );
        let subject = format!("space:{}", space.id);
        let organization = format!("space:{}", space.organization);
        let mut context =
            vec![json!({"user":subject,"relation":"template_team","object":organization})];
        if space.kind == crate::domain::SpaceKind::Personal {
            context.push(
                json!({"user":subject,"relation":"template_personal_team","object":organization}),
            );
        }
        let mut body = json!({"tuple_key":{"user":subject,"relation":"can_use",
            "object":format!("agent_template:{template}")},
            "contextual_tuples":{"tuple_keys":context}, "consistency":"HIGHER_CONSISTENCY"});
        self.pin_model(&mut body);
        let response = self
            .post(&format!("/stores/{}/check", self.store), body)
            .await?;
        response["allowed"]
            .as_bool()
            .context("missing OpenFGA decision")
    }
}
