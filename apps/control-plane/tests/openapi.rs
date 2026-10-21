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
        "get /me/spaces",
        "post /me/personal-space",
        "post /spaces",
        "delete /spaces/{id}",
        "get /deletions/{operation_id}",
        "put /spaces/{id}/roles/{role}/{user}",
        "delete /spaces/{id}/roles/{role}/{user}",
        "get /spaces/{id}/folders",
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
        "post /documents/{id}/processing",
        "get /documents/{id}/processing",
        "get /documents/{id}/preview",
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
        "post /admin/organizations",
        "post /authorize/platform",
        "post /authorize/space",
        "post /import-export/import",
    ]
    .into_iter()
    .map(String::from)
    .collect();
    assert_eq!(actual, expected);
    assert_eq!(
        api["paths"]["/control-plane/v1/admin/organizations"]["get"]["responses"]["400"]["content"]
            ["text/plain"]["schema"]["type"],
        "string"
    );
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
        json!([SpaceKind::Organization, SpaceKind::Team, SpaceKind::Project])
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
                    if status == "202" && operation["operationId"] == "delete_space" {
                        assert_eq!(
                            response["content"]["application/json"]["schema"]["$ref"],
                            "#/components/schemas/Receipt"
                        );
                    } else {
                        assert!(response.get("content").is_none());
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
fn document_metadata_and_mutation_routes_are_absent() {
    let api = schema();
    let paths = &api["paths"];
    assert!(paths.get("/control-plane/v1/documents").is_none());
    assert!(
        paths
            .get("/control-plane/v1/documents/{id}/ingest")
            .is_none()
    );
    assert!(paths.get("/control-plane/v1/documents/{id}").is_none());
    for name in ["CreateDocument", "CreatedDocument", "IngestRequest"] {
        assert!(api["components"]["schemas"].get(name).is_none());
    }
}

#[test]
fn folder_directory_contract_resolves_order_enum_and_metadata() {
    let api = schema();
    let schemas = &api["components"]["schemas"];
    assert_eq!(
        schemas["FolderOrder"]["enum"],
        json!(["name_asc", "name_desc", "created_asc", "created_desc"])
    );
    assert_eq!(
        schemas["Folder"]["properties"]["created_at"]["format"],
        "date-time"
    );
    let directory = &schemas["FolderDirectory"]["allOf"];
    assert!(
        directory
            .as_array()
            .unwrap()
            .iter()
            .any(|part| part["$ref"] == "#/components/schemas/FolderPage")
    );
    assert!(
        directory
            .as_array()
            .unwrap()
            .iter()
            .any(|part| part["properties"]["can_write"]["type"] == "boolean")
    );
    for field in ["items", "ancestors", "total", "offset", "limit"] {
        assert!(
            schemas["FolderPage"]["required"]
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
    assert_eq!(
        schemas["FileUpload"]["properties"]["file"],
        json!({"type":"string","format":"binary"})
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
