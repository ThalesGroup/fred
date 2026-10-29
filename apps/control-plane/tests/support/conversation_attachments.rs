// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

/// The session API needs a running agent instance; its product row is all attachments use.
async fn conversation(d: &Documents, owner: &str, space: Uuid) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into session_metadata (session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name) values ($1,$2,$3,$4,$5,'native','Assistant')")
        .bind(id).bind(owner).bind(space).bind(Uuid::new_v4()).bind(Uuid::new_v4())
        .execute(&d.e.pool).await.unwrap();
    id
}

fn attachments(space: Uuid, session: Uuid) -> String {
    format!("/spaces/{space}/sessions/{session}/attachments")
}

async fn attach(
    d: &Documents,
    user: &str,
    space: Uuid,
    session: Uuid,
    name: &str,
    bytes: &[u8],
) -> (u16, Value) {
    let mut body=format!("--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: text/plain\r\n\r\n").into_bytes();
    body.extend_from_slice(bytes);
    body.extend_from_slice(b"\r\n--fixture--\r\n");
    json_response(
        d.request(
            user,
            "POST",
            &attachments(space, session),
            Body::from(body),
            "multipart/form-data; boundary=fixture",
            Some(Uuid::new_v4()),
        )
        .await,
    )
    .await
}

async fn status(d: &Documents, user: &str, method: &str, path: &str) -> u16 {
    d.request(user, method, path, Body::empty(), "", None)
        .await
        .status()
        .as_u16()
}

async fn finish_processing(d: &Documents, document: Uuid) {
    sqlx::query("update document_processing set status='failed',error_code='fixture',completed_at=clock_timestamp() where document_id=$1 and status in ('pending','running')")
        .bind(document).execute(&d.e.pool).await.unwrap();
}

/// Deletion enabled, so delete routes reach authorization; immediate retention.
fn deletion() -> control_plane::lifecycle::Lifecycle {
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("PT0S").unwrap();
    lifecycle
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn reader_attaches_privately_to_own_conversation() {
    let (d, _p) = Box::pin(setup_with_lifecycle(deletion())).await;
    let team = d.folder.space_id;
    let bob = conversation(&d, "reader", team).await;
    let other = conversation(&d, "reader", team).await;

    // A team reader attaches to their own conversation; `fast` processing is requested with it.
    let response = d
        .request(
            "reader",
            "POST",
            &attachments(team, bob),
            Body::from("--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"notes.txt\"\r\n\r\nprivate\r\n--fixture--\r\n"),
            "multipart/form-data; boundary=fixture",
            Some(Uuid::new_v4()),
        )
        .await;
    let location = response.headers()["location"].to_str().unwrap().to_owned();
    let (code, receipt) = json_response(response).await;
    assert_eq!(code, 201, "{receipt}");
    assert_eq!(receipt["session_id"], bob.to_string());
    assert!(receipt["folder_id"].is_null());
    assert_eq!(receipt["processing_profile"], "fast");
    let key = receipt["request_key"].as_str().unwrap();
    assert_eq!(location, format!("../../../../document-uploads/{key}"));
    let document: Uuid = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let mut used = receipt["size"].as_i64().unwrap();
    let (code, tracked) = d
        .json(
            "reader",
            "GET",
            &format!("/document-uploads/{key}"),
            Value::Null,
        )
        .await;
    assert_eq!(code, 200, "{tracked}");
    assert_eq!(tracked["document_id"], document.to_string());

    let (code, listed) = d
        .json("reader", "GET", &attachments(team, bob), Value::Null)
        .await;
    assert_eq!(code, 200, "{listed}");
    assert_eq!(listed.as_array().unwrap().len(), 1);
    assert_eq!(listed[0]["document_id"], document.to_string());
    assert_eq!(listed[0]["name"], "notes.txt");

    // Names are unique per conversation, not per space.
    assert_eq!(
        attach(&d, "reader", team, bob, "notes.txt", b"again")
            .await
            .1["code"],
        "name_conflict"
    );
    let (code, sibling) = attach(&d, "reader", team, other, "notes.txt", b"again").await;
    assert_eq!(code, 201, "{sibling}");
    used += sibling["size"].as_i64().unwrap();

    // Other readers of the space find no such conversation; a team admin reads no content at all.
    for (user, refused) in [("alice", 404), ("writer", 404), ("admin", 403)] {
        assert_eq!(
            status(&d, user, "GET", &attachments(team, bob)).await,
            refused,
            "{user}"
        );
        assert_eq!(
            attach(&d, user, team, bob, "intruder.txt", b"x").await.0,
            refused,
            "{user}"
        );
        assert_eq!(
            status(
                &d,
                user,
                "DELETE",
                &format!("{}/{document}", attachments(team, bob))
            )
            .await,
            refused,
            "{user}"
        );
    }
    // The document routes do not serve an attachment, to anyone.
    for user in ["alice", "writer", "reader"] {
        for (method, path) in [
            ("DELETE", format!("/documents/{document}")),
            ("GET", format!("/documents/{document}/content")),
            ("GET", format!("/documents/{document}/processing")),
            ("GET", format!("/documents/{document}/preview")),
        ] {
            assert_eq!(status(&d, user, method, &path).await, 404, "{user} {path}");
        }
    }

    // Absent from the drive, its counters and upload receipts; present in the quota.
    let (code, entries) = d
        .json(
            "writer",
            "GET",
            &format!("/spaces/{team}/entries"),
            Value::Null,
        )
        .await;
    assert_eq!(code, 200, "{entries}");
    assert!(
        entries["items"]
            .as_array()
            .unwrap()
            .iter()
            .all(|e| e["kind"] == "folder")
    );
    let (code, storage) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{team}/storage"),
            Value::Null,
        )
        .await;
    assert_eq!(code, 200, "{storage}");
    assert_eq!(storage["documents"], 0);
    assert_eq!(storage["bytes"], 0);
    assert!(storage["types"].as_array().unwrap().is_empty());
    assert_eq!(storage["used_bytes"].as_i64().unwrap(), used);
    let (code, receipts) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{team}/document-uploads"),
            Value::Null,
        )
        .await;
    assert_eq!(code, 200, "{receipts}");
    assert!(receipts.as_array().unwrap().is_empty());
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn conversation_deletion_retires_and_purges_its_attachments() {
    use control_plane::lifecycle::{Receipt, Status, TargetKind, cleanup};
    let (d, _p) = Box::pin(setup_with_lifecycle(deletion())).await;
    let team = d.folder.space_id;
    let bob = conversation(&d, "reader", team).await;
    let (code, kept) = attach(&d, "reader", team, bob, "kept.txt", b"kept").await;
    assert_eq!(code, 201, "{kept}");
    let kept: Uuid = kept["document_id"].as_str().unwrap().parse().unwrap();
    let (code, removed) = attach(&d, "reader", team, bob, "removed.txt", b"gone").await;
    assert_eq!(code, 201, "{removed}");
    let removed: Uuid = removed["document_id"].as_str().unwrap().parse().unwrap();

    // The owner deletes one attachment through the conversation route.
    let path = format!("{}/{removed}", attachments(team, bob));
    assert_eq!(status(&d, "reader", "DELETE", &path).await, 409);
    finish_processing(&d, removed).await;
    let (code, accepted) = json_response(
        d.request("reader", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(code, 202, "{accepted}");
    assert_eq!(accepted["target_kind"], "document");
    let (code, replay) = json_response(
        d.request("reader", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(code, 202);
    assert_eq!(replay, accepted);
    assert_eq!(status(&d, "alice", "DELETE", &path).await, 404);

    // Deleting the conversation retires its remaining attachment and frees the quota at once.
    let (code, receipt) = json_response(
        d.request(
            "reader",
            "DELETE",
            &format!("/spaces/{team}/sessions/{bob}"),
            Body::empty(),
            "",
            None,
        )
        .await,
    )
    .await;
    assert_eq!(code, 202, "{receipt}");
    let operation: Uuid = receipt["id"].as_str().unwrap().parse().unwrap();
    let retired: Option<Uuid> = sqlx::query_scalar("select deletion_id from document where id=$1")
        .bind(kept)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(retired, Some(operation));
    assert_eq!(
        status(&d, "reader", "GET", &attachments(team, bob)).await,
        404
    );
    assert_eq!(
        attach(&d, "reader", team, bob, "late.txt", b"late").await.0,
        404
    );
    let (_, storage) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{team}/storage"),
            Value::Null,
        )
        .await;
    assert_eq!(storage["used_bytes"], 0);

    // Cleanup purges the attachment as a document, then blocks only on runtime history.
    finish_processing(&d, kept).await;
    for _ in 0..2 {
        cleanup::batch(&d.e.pool, &d.e.fga, operation)
            .await
            .unwrap();
    }
    let present: bool = sqlx::query_scalar("select exists(select 1 from document where id=$1)")
        .bind(kept)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(!present);
    let receipt: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(receipt.target_kind, TargetKind::Session);
    assert_eq!(receipt.documents_deleted, 1);
    assert_eq!(receipt.status, Status::Blocked);
    assert_eq!(
        receipt.error_code.as_deref(),
        Some("session_purge_unavailable")
    );
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn purged_attachment_receipt_answers_its_deleter_only() {
    use control_plane::lifecycle::cleanup;
    let (d, _p) = Box::pin(setup_with_lifecycle(deletion())).await;
    let team = d.folder.space_id;
    let bob = conversation(&d, "reader", team).await;
    let (code, attached) = attach(&d, "reader", team, bob, "gone.txt", b"gone").await;
    assert_eq!(code, 201, "{attached}");
    let document: Uuid = attached["document_id"].as_str().unwrap().parse().unwrap();
    finish_processing(&d, document).await;
    let path = format!("{}/{document}", attachments(team, bob));
    let (code, accepted) = json_response(
        d.request("reader", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(code, 202, "{accepted}");
    let operation: Uuid = accepted["id"].as_str().unwrap().parse().unwrap();
    cleanup::batch(&d.e.pool, &d.e.fga, operation)
        .await
        .unwrap();
    let present: bool = sqlx::query_scalar("select exists(select 1 from document where id=$1)")
        .bind(document)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(!present);

    // Without the row, another writer of the space cannot read the receipt; its deleter can.
    assert_eq!(
        status(&d, "writer", "DELETE", &format!("/documents/{document}")).await,
        404
    );
    let (code, replay) = json_response(
        d.request("reader", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(code, 200, "{replay}");
    assert_eq!(replay["id"], accepted["id"]);
    assert_eq!(replay["status"], "completed");
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn project_attachment_counts_against_its_team_quota() {
    let (d, _p) = Box::pin(setup()).await;
    let team = d.folder.space_id;
    let project = control_plane::spaces::create_space(
        &d.e.pool,
        &d.e.fga,
        "alice",
        control_plane::domain::SpaceKind::Project,
        team,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    // A team member stays local: reading the project needs its own role.
    crate::grant(&d.e, project.id, Role::Member, "reader").await;
    let session = conversation(&d, "reader", project.id).await;
    let (code, receipt) = attach(&d, "reader", project.id, session, "p.txt", b"12345").await;
    assert_eq!(code, 201, "{receipt}");
    let document: Uuid = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let (space, owner): (Uuid, Uuid) =
        sqlx::query_as("select space_id, quota_owner from document where id=$1")
            .bind(document)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!((space, owner), (project.id, team));
    for space in [team, project.id] {
        let (code, storage) = d
            .json(
                "reader",
                "GET",
                &format!("/spaces/{space}/storage"),
                Value::Null,
            )
            .await;
        assert_eq!(code, 200, "{storage}");
        assert_eq!(storage["used_bytes"], 5);
        assert_eq!(storage["documents"], 0);
    }
    // A session placed in another space is not a destination of this one.
    assert_eq!(
        attach(&d, "reader", team, session, "p.txt", b"12345")
            .await
            .0,
        404
    );
}
