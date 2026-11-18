// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! An immutable instance stores complete, typed public configuration. Secrets
//! are provisioned references and are never materialized into that snapshot.
use crate::{
    error::{AppError, AppResult},
    field_values::{self, FieldSpec},
};
use serde_json::Value;
use std::collections::{BTreeMap, HashSet};

pub(super) fn fields(schema: &Value) -> AppResult<Vec<FieldSpec>> {
    let fields: Vec<FieldSpec> = serde_json::from_value(
        schema.get("fields").cloned().unwrap_or(Value::Null),
    )
    .map_err(|_| AppError::Unprocessable("Invalid knowledge base configuration fields.".into()))?;
    let mut keys = HashSet::new();
    for field in &fields {
        if field.key.is_empty()
            || !keys.insert(&field.key)
            || (!field_values::textual(&field.kind)
                && !matches!(
                    field.kind.as_str(),
                    "boolean" | "integer" | "number" | "select" | "array" | "object"
                ))
            || (field.kind == "secret" && field.default.is_some())
        {
            return Err(AppError::Unprocessable(
                "Invalid or secret-bearing knowledge base configuration declaration.".into(),
            ));
        }
        if let Some(default) = &field.default {
            field_values::validate(field, default)?;
        }
    }
    Ok(fields)
}

pub(super) fn normalize(
    fields: &[FieldSpec],
    submitted: &Value,
    references: &BTreeMap<String, String>,
    profile: &str,
) -> AppResult<Value> {
    let supplied = submitted.as_object().ok_or_else(|| {
        AppError::Unprocessable("Knowledge base configuration must be an object.".into())
    })?;
    for key in supplied.keys() {
        let field = fields
            .iter()
            .find(|field| &field.key == key)
            .ok_or_else(|| AppError::Unprocessable("Unknown configuration field.".into()))?;
        if field.kind == "secret" {
            return Err(AppError::Unprocessable(
                "Secrets require a provisioned credential reference.".into(),
            ));
        }
    }
    if references.keys().any(|key| {
        !fields
            .iter()
            .any(|field| &field.key == key && field.kind == "secret")
    }) {
        return Err(AppError::Unprocessable(
            "Unknown credential reference field.".into(),
        ));
    }
    let mut normalized = serde_json::Map::new();
    for field in fields {
        if field.kind == "secret" {
            if field.required && !references.contains_key(&field.key) {
                return Err(AppError::Unprocessable(
                    "Required credential reference is missing.".into(),
                ));
            }
            continue;
        }
        // Processing already owns this choice; a declaration default must not
        // override the explicitly admitted processing profile.
        let profile_value = Value::String(profile.to_owned());
        let value = supplied.get(&field.key).or_else(|| {
            if field.key == "profile" {
                Some(&profile_value)
            } else {
                field.default.as_ref()
            }
        });
        match value {
            Some(value) => {
                field_values::validate(field, value)?;
                normalized.insert(field.key.clone(), value.clone());
            }
            None if field.required => {
                return Err(AppError::Unprocessable(
                    "Required configuration is missing.".into(),
                ));
            }
            None => {}
        }
    }
    Ok(Value::Object(normalized))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn schema() -> Value {
        json!({"fields":[
            {"key":"url","type":"url","required":true},
            {"key":"limit","type":"integer","min":1,"max":20,"default":5},
            {"key":"mode","type":"select","enum":["all","new"],"default":"all"},
            {"key":"profile","type":"select","enum":["fast","medium","rich"],"default":"medium"},
            {"key":"enabled","type":"boolean","default":true},
            {"key":"headers","type":"object"},
            {"key":"paths","type":"array","item_type":"string"},
            {"key":"name","type":"string","pattern":"[a-z]+"},
            {"key":"password","type":"secret","required":true}
        ]})
    }
    #[test]
    fn knowledge_base_configuration_materializes_defaults_without_secrets() {
        let specs = fields(&schema()).unwrap();
        let references = BTreeMap::from([("password".into(), "provisioned".into())]);
        let normalized = normalize(
            &specs,
            &json!({"url":"https://source/<tools>"}),
            &references,
            "rich",
        )
        .unwrap();
        assert_eq!(
            normalized,
            json!({"url":"https://source/<tools>","limit":5,"mode":"all","profile":"rich","enabled":true})
        );
    }
    #[test]
    fn knowledge_base_configuration_rejects_invalid_values_and_plaintext_secrets() {
        let specs = fields(&schema()).unwrap();
        let references = BTreeMap::from([("password".into(), "provisioned".into())]);
        for (key, value) in [
            ("url", Value::Null),
            ("url", json!(false)),
            ("url", json!({"nested":"value"})),
            ("limit", json!("5")),
            ("limit", json!(1.5)),
            ("limit", json!(0)),
            ("limit", json!(21)),
            ("mode", json!("unsupported")),
            ("enabled", json!(1)),
            ("headers", json!({"nested":{}})),
            ("paths", json!([1])),
            ("paths", json!([["nested"]])),
            ("name", json!("UPPER")),
            ("password", json!("plaintext")),
            ("password", Value::Null),
            ("unknown", json!(true)),
        ] {
            let mut values = json!({"url":"https://source"});
            values[key] = value;
            assert!(
                normalize(&specs, &values, &references, "medium").is_err(),
                "{values}"
            );
        }
        assert!(normalize(&specs, &json!({}), &references, "medium").is_err());
        assert!(
            normalize(
                &specs,
                &json!({"url":"https://source"}),
                &BTreeMap::new(),
                "medium"
            )
            .is_err()
        );
    }
    #[test]
    fn knowledge_base_declaration_defaults_are_validated_before_storage() {
        for (index, default) in [(1, json!(0)), (2, json!("wrong")), (8, json!("plaintext"))] {
            let mut schema = schema();
            schema["fields"][index]["default"] = default;
            assert!(fields(&schema).is_err());
        }
    }
}
