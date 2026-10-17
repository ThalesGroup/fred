// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The offline contract must describe the wire format, not just compile.
use fred_manager::{
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
        Command::new(env!("CARGO_BIN_EXE_fred-manager"))
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
                path.strip_prefix("/fred-manager/v1").unwrap()
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
        "get /spaces/{id}/documents",
        "post /folders",
        "patch /folders/{id}",
        "delete /folders/{id}",
        "post /documents",
        "get /documents/{id}",
        "patch /documents/{id}",
        "delete /documents/{id}",
        "post /documents/{id}/ingest",
        "post /authorize/document",
        "post /authorize/scope",
        "get /users/platform-roles",
        "put /users/{user}/platform-roles/{role}",
        "delete /users/{user}/platform-roles/{role}",
        "get /admin/teams",
        "post /authorize/platform",
        "post /authorize/space",
        "post /import-export/import",
    ]
    .into_iter()
    .map(String::from)
    .collect();
    assert_eq!(actual, expected);
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
            Role::Owner,
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
    for (wrapper, inner, extra) in [
        ("MySpace", "Space", "roles"),
        ("CreatedDocument", "Document", "source_key"),
    ] {
        assert_eq!(
            schemas[wrapper]["allOf"][0]["$ref"],
            format!("#/components/schemas/{inner}")
        );
        assert!(
            schemas[wrapper]["allOf"][1]["properties"]
                .get(extra)
                .is_some()
        );
    }
}

#[test]
fn upload_optional_body_and_empty_responses_match_the_http_contract() {
    let api = schema();
    let import = &api["paths"]["/fred-manager/v1/import-export/import"]["post"];
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
        api["paths"]["/fred-manager/v1/users/{user}/platform-roles/{role}"]["delete"]["responses"]
            ["404"]["content"]["application/json"]["schema"]["$ref"],
        "#/components/schemas/ErrorBody"
    );
    let ingest = &api["paths"]["/fred-manager/v1/documents/{id}/ingest"]["post"];
    assert_eq!(ingest["requestBody"]["required"], false);
    assert_eq!(
        ingest["requestBody"]["content"]["application/json"]["schema"]["$ref"],
        "#/components/schemas/IngestRequest"
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
fn platform_role_alias_descriptions_match_the_parser() {
    let schema = schema();
    for method in ["put", "delete"] {
        let parameters = schema["paths"]["/fred-manager/v1/users/{user}/platform-roles/{role}"]
            [method]["parameters"]
            .as_array()
            .unwrap();
        let role = parameters.iter().find(|p| p["name"] == "role").unwrap();
        assert_eq!(
            role["description"],
            "Also accepts the owner and observer aliases."
        );
    }
    for accepted in ["owner", "observer"] {
        assert!(PlatformRole::parse(accepted).is_some());
    }
    for removed in ["admin", "platform_admin", "team_manager"] {
        assert!(PlatformRole::parse(removed).is_none());
    }
}
