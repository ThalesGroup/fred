// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The offline contract must describe the wire format, not just compile.
use control_plane::{
    api,
    domain::{Role, Space, SpaceKind},
    roles::PlatformRole,
};
use serde_json::{Value, json};
use std::{collections::BTreeSet, process::Command};
use uuid::Uuid;

fn schema() -> Value {
    serde_json::to_value(api::openapi()).unwrap()
}

#[test]
fn attachment_readiness_is_required_and_independent_of_processing() {
    let api = schema();
    let attachment = &api["components"]["schemas"]["Attachment"];
    assert!(
        attachment["required"]
            .as_array()
            .unwrap()
            .contains(&json!("ready"))
    );
    assert_eq!(attachment["properties"]["ready"]["type"], "boolean");
    assert!(attachment["properties"].get("processing").is_some());
}

#[test]
fn processing_descriptor_requires_nullable_placement_fields() {
    let api = schema();
    let descriptor = &api["components"]["schemas"]["Descriptor"];
    let required = descriptor["required"].as_array().unwrap();
    for field in ["folder_id", "folder_path", "session_id"] {
        assert!(required.contains(&json!(field)), "{field}");
        let types = descriptor["properties"][field]["type"].as_array().unwrap();
        assert!(
            types.contains(&json!("string")) && types.contains(&json!("null")),
            "{field}"
        );
    }
}

#[test]
fn cli_help_exposes_authenticated_import_without_operator_creation() {
    let output = Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("--help")
        .env("CONFIG_FILE", "/nonexistent/manager-configuration")
        .env("ENV_FILE", "/nonexistent/manager-env")
        .output()
        .unwrap();
    assert!(output.status.success());
    let help = String::from_utf8(output.stdout).unwrap();
    assert!(help.contains("import-provisioning"));
    assert!(!help.contains("create-org"));
}

#[test]
fn offline_command_is_deterministic_without_runtime_configuration() {
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_control-plane"))
            .arg("generate-openapi")
            .env("CONFIG_FILE", "/nonexistent/manager-configuration")
            .env("ENV_FILE", "/nonexistent/manager-env")
            .output()
            .unwrap()
    };
    let first = run();
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    assert!(first.stderr.is_empty());
    assert_eq!(first.stdout, run().stdout);
    assert_eq!(
        serde_json::from_slice::<Value>(&first.stdout).unwrap(),
        schema()
    );
}

#[test]
fn all_registered_routes_have_a_unique_operation_and_auth_contract() {
    let api = schema();
    let paths = api["paths"].as_object().unwrap();
    let mut actual = BTreeSet::new();
    let mut ids = BTreeSet::new();
    for (path, item) in paths {
        for (method, operation) in item.as_object().unwrap() {
            actual.insert(format!(
                "{method} {}",
                path.strip_prefix("/control-plane/v1").unwrap()
            ));
            assert!(ids.insert(operation["operationId"].as_str().unwrap()));
            for param in operation["parameters"].as_array().into_iter().flatten() {
                if param["in"] == "path" {
                    assert!(path.contains(&format!("{{{}}}", param["name"].as_str().unwrap())));
                    assert_eq!(param["required"], true);
                }
            }
            if path.ends_with("/healthz") || path.ends_with("/frontend/config") {
                assert_eq!(operation["security"], json!([{}]));
            } else {
                assert!(operation.get("security").is_none());
                assert!(operation["responses"].get("401").is_some());
            }
        }
    }
    let expected = [
        "get /healthz",
        "get /frontend/config",
        "get /me/onboarding",
        "post /gcu",
        "post /bootstrap/platform-admin",
        "get /me",
        "get /users/me/preferences",
        "patch /users/me/preferences",
        "get /me/spaces",
        "post /me/personal-space",
        "post /spaces",
        "delete /spaces/{id}",
        "get /deletions/{operation_id}",
        "put /spaces/{id}/roles/{role}/{user}",
        "delete /spaces/{id}/roles/{role}/{user}",
        "post /folders",
        "patch /folders/{id}",
        "delete /folders/{id}",
        "post /folders/{id}/documents",
        "post /folders/{id}/documents/preflight",
        "get /spaces/{id}/entries",
        "get /spaces/{id}/storage",
        "get /spaces/{id}/document-uploads",
        "get /document-uploads/{id}",
        "put /document-uploads/{id}/acknowledgment",
        "get /documents/{id}/content",
        "delete /documents/{id}",
        "post /documents/{id}/processing",
        "get /documents/{id}/processing",
        "get /documents/{id}/preview",
        "put /documents/{id}/retrievable",
        "get /document-processing/retrievable/{id}",
        "post /document-processing/retrievable/{id}",
        "get /document-processing/{id}/work",
        "post /document-processing/{id}/claim",
        "post /document-processing/{id}/commit",
        "post /document-processing/{id}/abandon",
        "post /document-processing/{id}/vectors",
        "get /document-processing/{id}/original",
        "get /document-processing/cleanup",
        "post /document-processing/cleanup",
        "post /authorize/document",
        "post /authorize/scope",
        "get /users/platform-roles",
        "put /users/{user}/platform-roles/{role}",
        "delete /users/{user}/platform-roles/{role}",
        "get /admin/teams",
        "get /admin/organizations",
        "get /admin/organizations/candidates",
        "post /admin/organizations",
        "get /admin/organizations/{id}",
        "patch /admin/organizations/{id}",
        "post /authorize/platform",
        "post /authorize/space",
        "post /import-export/import",
        "get /organizations/{organization_id}/agents",
        "get /organizations/{organization_id}/capabilities",
        "post /organizations/{organization_id}/capabilities/{runtime_id}/refresh",
        "put /organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/default-on",
        "get /organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/revoke-impact",
        "get /organizations/{organization_id}/models",
        "get /organizations/{organization_id}/model-policy",
        "put /organizations/{organization_id}/model-policy",
        "post /organizations/{organization_id}/model-sources/{source_id}/refresh",
        "get /spaces/{space_id}/agent-templates",
        "post /spaces/{space_id}/agent-instances",
        "get /spaces/{space_id}/agent-instances",
        "get /spaces/{space_id}/agent-instances/{agent_instance_id}",
        "get /spaces/{space_id}/agent-instances/{agent_instance_id}/runtime",
        "post /spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution",
        "patch /spaces/{space_id}/agent-instances/{agent_instance_id}",
        "delete /spaces/{space_id}/agent-instances/{agent_instance_id}",
        "post /spaces/{space_id}/sessions",
        "get /spaces/{space_id}/sessions",
        "get /spaces/{space_id}/sessions/{session_id}",
        "patch /spaces/{space_id}/sessions/{session_id}",
        "delete /spaces/{space_id}/sessions/{session_id}",
        "post /spaces/{space_id}/sessions/{session_id}/attachments",
        "get /spaces/{space_id}/sessions/{session_id}/attachments",
        "delete /spaces/{space_id}/sessions/{session_id}/attachments/{document_id}",
        "get /organizations/{organization_id}/supervision",
        "get /organizations/{organization_id}/supervision/teams/{team_id}",
        "put /organizations/{organization_id}/agents/{agent_id}/default-on",
        "post /agents/execute/stream",
    ]
    .into_iter()
    .map(String::from)
    .collect();
    assert_eq!(actual, expected);
    // One error format: every error answer is ErrorBody JSON, and any route with
    // parameters or a body declares the extractors' 422.
    for (path, item) in api["paths"].as_object().unwrap() {
        for (method, operation) in item.as_object().unwrap() {
            for (status, response) in operation["responses"].as_object().unwrap() {
                if status.starts_with('4') || status.starts_with('5') {
                    let content = response["content"].as_object().unwrap();
                    assert_eq!(
                        content.keys().collect::<Vec<_>>(),
                        ["application/json"],
                        "{method} {path} {status}"
                    );
                    assert_eq!(
                        content["application/json"]["schema"]["$ref"],
                        "#/components/schemas/ErrorBody",
                        "{method} {path} {status}"
                    );
                }
            }
            let inputs = operation["parameters"]
                .as_array()
                .is_some_and(|p| !p.is_empty())
                || operation["requestBody"].is_object();
            if inputs {
                assert!(operation["responses"]["422"].is_object(), "{method} {path}");
            }
        }
    }
    assert_eq!(api["security"], json!([{"bearer": []}]));
    assert_eq!(
        api["components"]["securitySchemes"]["bearer"],
        json!({"type":"http","scheme":"bearer"})
    );
}

#[test]
fn schemas_preserve_serialized_roles_nullable_fields_and_flattening() {
    let api = schema();
    let schemas = &api["components"]["schemas"];
    assert_eq!(schemas["PlatformRole"]["enum"], json!(PlatformRole::ALL));
    assert_eq!(
        schemas["Role"]["enum"],
        json!([
            Role::Member,
            Role::Editor,
            Role::Admin,
            Role::Analyst,
            Role::OrganizationOwner,
            Role::PersonalSpaceCreator
        ])
    );
    assert_eq!(
        schemas["SpaceKind"]["enum"],
        json!([
            SpaceKind::Organization,
            SpaceKind::Team,
            SpaceKind::Project,
            SpaceKind::Personal
        ])
    );
    let space = Space {
        id: Uuid::nil(),
        kind: SpaceKind::Organization,
        name: "Demo".into(),
        parent_id: None,
        personal_owner: None,
        path: vec![Uuid::nil()],
        organization: Uuid::nil(),
    };
    let wire = serde_json::to_value(space).unwrap();
    let required: BTreeSet<_> = schemas["Space"]["required"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap())
        .collect();
    assert_eq!(
        required,
        wire.as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect()
    );
    for name in ["parent_id", "personal_owner"] {
        assert!(wire[name].is_null());
        assert!(
            schemas["Space"]["properties"][name]["type"]
                .as_array()
                .unwrap()
                .contains(&json!("null"))
        );
    }
    assert_eq!(
        schemas["MySpace"]["allOf"][0]["$ref"],
        "#/components/schemas/Space"
    );
    assert!(
        schemas["MySpace"]["allOf"][1]["properties"]
            .get("roles")
            .is_some()
    );
}

#[test]
fn upload_and_empty_responses_match_the_http_contract() {
    let api = schema();
    let import = &api["paths"]["/control-plane/v1/import-export/import"]["post"];
    assert_eq!(import["requestBody"]["required"], true);
    assert_eq!(
        import["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"],
        "#/components/schemas/ProvisioningUpload"
    );
    assert_eq!(
        api["components"]["schemas"]["ProvisioningUpload"]["properties"]["file"],
        json!({"type":"string","format":"binary"})
    );
    assert_eq!(
        api["components"]["schemas"]["ProvisioningUpload"]["required"],
        json!(["file"])
    );
    assert_eq!(
        import["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],
        "#/components/schemas/Report"
    );
    assert!(import["responses"].get("202").is_none());
    for status in ["400", "401", "403", "409", "413", "422", "500", "503"] {
        assert_eq!(
            import["responses"][status]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorBody"
        );
    }
    assert_eq!(
        api["paths"]["/control-plane/v1/users/{user}/platform-roles/{role}"]["delete"]["responses"]
            ["404"]["content"]["application/json"]["schema"]["$ref"],
        "#/components/schemas/ErrorBody"
    );
    for item in api["paths"].as_object().unwrap().values() {
        for operation in item.as_object().unwrap().values() {
            for status in ["202", "204"] {
                if let Some(response) = operation["responses"].get(status) {
                    if status == "202"
                        && matches!(
                            operation["operationId"].as_str(),
                            Some(
                                "delete_space"
                                    | "delete_document"
                                    | "delete_session"
                                    | "delete_attachment"
                            )
                        )
                    {
                        assert_eq!(
                            response["content"]["application/json"]["schema"]["$ref"],
                            "#/components/schemas/Receipt"
                        );
                    } else {
                        assert!(
                            response.get("content").is_none(),
                            "{} {status}",
                            operation["operationId"]
                        );
                    }
                }
            }
        }
    }
}

#[test]
fn role_names_are_exact_and_unaliased() {
    let schema = schema();
    assert_eq!(
        schema["components"]["schemas"]["PlatformRole"]["enum"],
        json!([
            "platform_owner",
            "platform_observer",
            "feature_manager",
            "prompt_editor"
        ])
    );
    assert!(
        schema["components"]["schemas"]["Role"]["enum"]
            .as_array()
            .unwrap()
            .contains(&json!("organization_owner"))
    );
    for name in [
        "platform_owner",
        "platform_observer",
        "feature_manager",
        "prompt_editor",
    ] {
        assert_eq!(PlatformRole::parse(name).unwrap().relation(), name);
    }
    for refused in [
        "owner",
        "observer",
        "admin",
        "platform_admin",
        "team_manager",
    ] {
        assert!(PlatformRole::parse(refused).is_none());
    }
    assert!(Role::parse("owner").is_none());
    assert_eq!(
        Role::parse("organization_owner").map(Role::as_str),
        Some("organization_owner")
    );
}

#[test]
fn document_deletion_is_exposed_without_legacy_metadata_and_ingest_routes() {
    let api = schema();
    let paths = &api["paths"];
    assert!(paths.get("/control-plane/v1/documents").is_none());
    assert!(
        paths
            .get("/control-plane/v1/documents/{id}/ingest")
            .is_none()
    );
    let document = paths["/control-plane/v1/documents/{id}"]
        .as_object()
        .unwrap();
    assert_eq!(
        document.keys().map(String::as_str).collect::<Vec<_>>(),
        ["delete"]
    );
    for status in ["200", "202"] {
        assert_eq!(
            document["delete"]["responses"][status]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/Receipt"
        );
    }
    for name in ["CreateDocument", "CreatedDocument", "IngestRequest"] {
        assert!(api["components"]["schemas"].get(name).is_none());
    }
}

#[test]
fn directory_contract_resolves_order_enum_and_metadata() {
    let api = schema();
    let schemas = &api["components"]["schemas"];
    assert!(
        api["paths"]
            .get("/control-plane/v1/spaces/{id}/folders")
            .is_none()
    );
    for removed in [
        "FolderDirectory",
        "FolderPage",
        "FolderOrder",
        "FolderQuery",
    ] {
        assert!(schemas.get(removed).is_none());
    }
    assert_eq!(
        schemas["EntryOrder"]["enum"],
        json!([
            "name_asc",
            "name_desc",
            "created_asc",
            "created_desc",
            "size_asc",
            "size_desc"
        ])
    );
    assert_eq!(
        schemas["Folder"]["properties"]["created_at"]["format"],
        "date-time"
    );
    assert_eq!(
        schemas["Directory"]["properties"]["can_write"]["type"],
        "boolean"
    );
    for field in [
        "items",
        "ancestors",
        "total",
        "offset",
        "limit",
        "processing",
    ] {
        assert!(
            schemas["Directory"]["required"]
                .as_array()
                .unwrap()
                .contains(&json!(field))
        );
    }
}

#[test]
fn configuration_schema_is_generated_offline_and_matches_the_chart_input() {
    let output = Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("generate-config-schema")
        .env("CONFIG_FILE", "/does/not/exist")
        .env("ENV_FILE", "/does/not/exist")
        .output()
        .unwrap();
    assert!(output.status.success());
    let actual: Value = serde_json::from_slice(&output.stdout).unwrap();
    let committed: Value =
        serde_json::from_str(include_str!("../config/schema/configuration.schema.json")).unwrap();
    assert_eq!(actual, committed);
    assert_eq!(
        actual["$defs"]["LifecycleConfig"]["properties"]["sweep_interval"]["type"],
        "string"
    );
    assert_eq!(
        actual["$defs"]["LifecycleConfig"]["properties"]["sweep_interval"]["default"],
        "PT10M"
    );
}

#[test]
fn migration_command_requires_only_database_url_and_redacts_errors() {
    for url in [None, Some("invalid://private-password@invalid")] {
        let mut command = Command::new(env!("CARGO_BIN_EXE_control-plane"));
        command
            .arg("migrate")
            .env("CONFIG_FILE", "/nonexistent/manager-configuration")
            .env("ENV_FILE", "/nonexistent/manager-env")
            .env_remove("DATABASE_URL");
        if let Some(url) = url {
            command.env("DATABASE_URL", url);
        }
        let output = command.output().unwrap();
        assert!(!output.status.success());
        let error = String::from_utf8_lossy(&output.stderr);
        assert!(
            error.contains(if url.is_none() {
                "DATABASE_URL is required"
            } else {
                "migration database connection failed"
            }),
            "{error}"
        );
        assert!(!error.contains("private-password"));
        assert!(!error.contains("/nonexistent"));
    }
}

#[test]
fn document_receipts_and_lifecycle_receipts_have_distinct_generated_contracts() {
    let api = schema();
    for (path, method) in [
        ("/folders/{id}/documents/preflight", "post"),
        ("/spaces/{id}/entries", "get"),
        ("/spaces/{id}/storage", "get"),
        ("/spaces/{id}/document-uploads", "get"),
        ("/document-uploads/{id}", "get"),
        ("/documents/{id}/content", "get"),
    ] {
        // Ambiguous canonical organization context is an explicit conflict.
        assert!(
            api["paths"][format!("/control-plane/v1{path}")][method]["responses"]
                .get("409")
                .is_some()
        );
    }
    let upload = &api["paths"]["/control-plane/v1/folders/{id}/documents"]["post"];
    assert_eq!(
        upload["responses"]["201"]["content"]["application/json"]["schema"]["$ref"],
        "#/components/schemas/UploadReceipt"
    );
    let schemas = &api["components"]["schemas"];
    assert!(schemas["UploadReceipt"]["properties"]["request_key"].is_object());
    assert!(schemas["Receipt"]["properties"]["target_id"].is_object());
    let file = &schemas["FileUpload"]["properties"]["file"];
    assert_eq!(
        (&file["type"], &file["format"]),
        (&json!("string"), &json!("binary"))
    );
    assert!(
        schemas["EntryOrder"]["enum"]
            .as_array()
            .unwrap()
            .contains(&json!("size_desc"))
    );
    for status in [
        "400", "401", "403", "404", "408", "409", "413", "422", "429", "503",
    ] {
        assert_eq!(
            upload["responses"][status]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ErrorBody"
        );
    }
}

#[test]
fn instance_operations_and_nullable_patch_match_the_wire_contract() {
    use control_plane::agent_instances::http::UpdateAgentInstanceRequest;
    let api = schema();
    let schemas = &api["components"]["schemas"];
    let collection = "/control-plane/v1/spaces/{space_id}/agent-instances";
    let instance = format!("{collection}/{{agent_instance_id}}");
    let templates = "/control-plane/v1/spaces/{space_id}/agent-templates";
    for (path, method, status, response) in [
        (templates, "get", "200", "AgentTemplateSummary"),
        (collection, "post", "201", "ManagedAgentInstanceSummary"),
        (collection, "get", "200", "ManagedAgentInstanceSummary"),
        (&instance, "get", "200", "ManagedAgentInstanceSummary"),
        (&instance, "patch", "200", "ManagedAgentInstanceSummary"),
        (&instance, "delete", "204", ""),
    ] {
        let op = &api["paths"][path][method];
        assert!(op.is_object(), "{method} {path}");
        for error in ["400", "401", "403", "404", "409", "422", "500", "503"] {
            assert_eq!(
                op["responses"][error]["content"]["application/json"]["schema"]["$ref"],
                "#/components/schemas/ErrorBody",
                "{method} {path} {error}"
            );
        }
        let success = &op["responses"][status];
        if status == "204" {
            assert!(success.get("content").is_none());
        } else {
            let body = &success["content"]["application/json"]["schema"];
            let body = if method == "get" && path != instance {
                assert_eq!(body["type"], "array");
                &body["items"]
            } else {
                body
            };
            assert_eq!(body["$ref"], format!("#/components/schemas/{response}"));
        }
    }
    for (method, name) in [
        ("post", "CreateAgentInstanceRequest"),
        ("patch", "UpdateAgentInstanceRequest"),
    ] {
        let path = if method == "post" {
            collection
        } else {
            &instance
        };
        assert_eq!(
            api["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]["$ref"],
            format!("#/components/schemas/{name}")
        );
        assert_eq!(schemas[name]["additionalProperties"], false);
    }
    let create = schemas["CreateAgentInstanceRequest"]["required"]
        .as_array()
        .unwrap();
    assert_eq!(
        create,
        json!(["template_id", "display_name", "usage_statement"])
            .as_array()
            .unwrap()
    );
    let patch = &schemas["UpdateAgentInstanceRequest"];
    assert!(patch["required"].as_array().is_none_or(Vec::is_empty));
    fn nullable(value: &Value) -> bool {
        value["type"]
            .as_array()
            .is_some_and(|types| types.contains(&json!("null")))
            || value["type"] == "null"
            || ["oneOf", "anyOf"].iter().any(|k| {
                value[k]
                    .as_array()
                    .is_some_and(|variants| variants.iter().any(nullable))
            })
    }
    for (name, property) in patch["properties"].as_object().unwrap() {
        assert!(nullable(property), "{name}: {property}");
    }
    assert_eq!(
        schemas["AgentInstanceStatus"]["enum"],
        json!(["enabled", "disabled"])
    );
    let omitted: UpdateAgentInstanceRequest = serde_json::from_value(json!({})).unwrap();
    assert!(omitted.tuning_field_values.is_none());
    assert!(omitted.capability_ids.is_none());
    assert!(omitted.recommended_chat_profile_id.is_none());
    let cleared:UpdateAgentInstanceRequest=serde_json::from_value(json!({"tuning_field_values":null,"capability_ids":null,"capability_config_values":null,"recommended_chat_profile_id":null})).unwrap();
    assert!(matches!(cleared.tuning_field_values, Some(None)));
    assert!(matches!(cleared.capability_ids, Some(None)));
    assert!(matches!(cleared.capability_config_values, Some(None)));
    assert!(matches!(cleared.recommended_chat_profile_id, Some(None)));
    let empty: UpdateAgentInstanceRequest =
        serde_json::from_value(json!({"tuning_field_values":{},"capability_ids":[]})).unwrap();
    assert!(empty.tuning_field_values.unwrap().unwrap().is_empty());
    assert!(empty.capability_ids.unwrap().unwrap().is_empty());
}
