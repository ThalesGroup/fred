// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

/// The session API needs a running agent instance; its product row is all attachments use.
async fn conversation(d: &Documents, owner: &str, space: Uuid) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into session_metadata (session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values ($1,$2,$3,$4,$5,'native','Assistant',1)")
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
    attach_request(
        d,
        user,
        &attachments(space, session),
        name,
        bytes,
        Uuid::new_v4(),
    )
    .await
}

async fn attach_request(
    d: &Documents,
    user: &str,
    path: &str,
    name: &str,
    bytes: &[u8],
    key: Uuid,
) -> (u16, Value) {
    let mut body=format!("--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: text/plain\r\n\r\n").into_bytes();
    body.extend_from_slice(bytes);
    body.extend_from_slice(b"\r\n--fixture--\r\n");
    json_response(
        d.request(
            user,
            "POST",
            path,
            Body::from(body),
            "multipart/form-data; boundary=fixture",
            Some(key),
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
async fn conversation_limits_include_concurrent_pending_reservations() {
    use control_plane::documents::config::Limits;
    for (files, bytes, code) in [
        (1, 100, "conversation_files_exceeded"),
        (100, 4, "conversation_bytes_exceeded"),
    ] {
        let limits = Limits {
            conversation_files: files,
            conversation_bytes: bytes,
            ..Default::default()
        };
        let (d, _p) = Box::pin(setup_with_content_limits(deletion(), limits)).await;
        let d = Arc::new(d);
        let space = d.folder.space_id;
        let session = conversation(&d, "reader", space).await;
        let gate = Arc::new(crate::support::Gate::default());
        d.proxy.fault.lock().await.hold_put = Some(gate.clone());
        let sending = d.clone();
        let first = tokio::spawn(async move {
            attach(&sending, "reader", space, session, "first.csv", b"1234").await
        });
        tokio::time::timeout(Duration::from_secs(10), gate.entered.notified())
            .await
            .unwrap();
        let second = attach(&d, "reader", space, session, "second.csv", b"5").await;
        gate.release.notify_one();
        let first = first.await.unwrap();
        assert_eq!(first.0, 201, "{first:?}");
        assert_eq!(second.0, 422, "{second:?}");
        assert_eq!(second.1["code"], code);
        let count: i64 =
            sqlx::query_scalar("select count(*) from document_upload where session_id=$1")
                .bind(session)
                .fetch_one(&d.e.pool)
                .await
                .unwrap();
        assert_eq!(count, 1);
        // Limits are per conversation and do not apply to the drive.
        let other = conversation(&d, "reader", space).await;
        assert_eq!(
            attach(&d, "reader", space, other, "first.csv", b"1234")
                .await
                .0,
            201
        );
        assert_eq!(
            d.upload("writer", "drive.csv", b"12345", Uuid::new_v4(), None)
                .await
                .0,
            201
        );
    }
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn conversation_limit_counts_stored_once_replays_full_and_releases_retired() {
    let limits = control_plane::documents::config::Limits {
        conversation_files: 2,
        conversation_bytes: 6,
        ..Default::default()
    };
    let (d, _p) = Box::pin(setup_with_content_limits(deletion(), limits)).await;
    let space = d.folder.space_id;
    let session = conversation(&d, "reader", space).await;
    let path = attachments(space, session);
    let key = Uuid::new_v4();
    let first = attach_request(&d, "reader", &path, "first.csv", b"123", key).await;
    assert_eq!(first.0, 201, "{first:?}");
    assert_eq!(
        attach(&d, "reader", space, session, "second.csv", b"456")
            .await
            .0,
        201
    );
    assert_eq!(
        attach(&d, "reader", space, session, "third.csv", b"7")
            .await
            .0,
        422
    );
    let replay = attach_request(&d, "reader", &path, "first.csv", b"123", key).await;
    assert_eq!(replay.0, 200, "{replay:?}");
    assert_eq!(replay.1["document_id"], first.1["document_id"]);
    let other = conversation(&d, "reader", space).await;
    let misplaced = attach_request(
        &d,
        "reader",
        &attachments(space, other),
        "first.csv",
        b"123",
        key,
    )
    .await;
    assert_eq!(misplaced.0, 409);
    assert_eq!(misplaced.1["code"], "idempotency_conflict");
    let document: Uuid = first.1["document_id"].as_str().unwrap().parse().unwrap();
    finish_processing(&d, document).await;
    assert_eq!(
        status(&d, "reader", "DELETE", &format!("{path}/{document}")).await,
        202
    );
    // Physical cleanup has not run, but logical capacity has already been released.
    assert_eq!(
        attach(&d, "reader", space, session, "replacement.csv", b"789")
            .await
            .0,
        201
    );
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn failed_attachment_retry_reserves_once_and_keeps_idempotency() {
    let limits = control_plane::documents::config::Limits {
        conversation_files: 1,
        conversation_bytes: 4,
        ..Default::default()
    };
    let (d, _p) = Box::pin(setup_with_content_limits(deletion(), limits)).await;
    let space = d.folder.space_id;
    let session = conversation(&d, "reader", space).await;
    let path = attachments(space, session);
    let failed_key = Uuid::new_v4();
    d.proxy.fault.lock().await.deny_put = true;
    assert_eq!(
        attach_request(&d, "reader", &path, "retry.csv", b"1234", failed_key)
            .await
            .0,
        503
    );
    d.proxy.fault.lock().await.deny_put = false;
    let retry_path = format!("{path}?retry_of={failed_key}");
    let retry_key = Uuid::new_v4();
    let (first, replay) = tokio::join!(
        attach_request(&d, "reader", &retry_path, "retry.csv", b"1234", retry_key),
        attach_request(&d, "reader", &retry_path, "retry.csv", b"1234", retry_key)
    );
    assert!(first.0 == 201 || replay.0 == 201, "{first:?} {replay:?}");
    assert!([200, 201, 409].contains(&first.0) && [200, 201, 409].contains(&replay.0));
    let replay = attach_request(&d, "reader", &retry_path, "retry.csv", b"1234", retry_key).await;
    assert_eq!(replay.0, 200, "{replay:?}");
    let superseded = attach_request(
        &d,
        "reader",
        &retry_path,
        "retry.csv",
        b"1234",
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(superseded.1["code"], "retry_superseded");
    let count: i64 = sqlx::query_scalar("select count(*) from document where session_id=$1")
        .bind(session)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(count, 1);
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn tabular_attachments_publish_without_vectors_and_purge_all_artifacts() {
    use control_plane::lifecycle::cleanup;
    let (d, p) = Box::pin(setup_with_lifecycle(deletion())).await;
    let space = d.folder.space_id;
    let session = conversation(&d, "reader", space).await;
    for name in ["sales.csv", "workbook.xlsx"] {
        let (code, receipt) = attach(&d, "reader", space, session, name, b"source").await;
        assert_eq!(code, 201, "{receipt}");
        let operation = receipt["processing"]["id"]
            .as_str()
            .unwrap()
            .parse()
            .unwrap();
        let work = store::row(&d.e.pool, operation)
            .await
            .unwrap()
            .work(p.installation);
        for stage in [Stage::Preparation, Stage::Extraction] {
            let descriptor = p
                .claim(claim(&work, stage, Uuid::new_v4(), 1))
                .await
                .unwrap();
            commit(&p, &descriptor, &[("policy.json", b"{}")], 0).await;
        }
        let descriptor = p
            .claim(claim(&work, Stage::Indexing, Uuid::new_v4(), 1))
            .await
            .unwrap();
        let table_count = if name.ends_with("xlsx") { 2 } else { 1 };
        let tables: Vec<Value> = (0..table_count).map(|i| json!({
            "dataset_uid": work.document_id, "object_key":format!("datasets/{i}.parquet"),
            "source_revision":work.original_sha256, "format":"parquet", "file_size_bytes":4,
            "row_count":2, "query_alias":format!("table_{i}"), "sheet":format!("Sheet{i}"), "table_id":format!("t{i}")
        })).collect();
        let extensions = if table_count == 1 {
            json!({"tabular_v1":tables[0]})
        } else {
            json!({"tabular_multi_v1":{"tables":tables}})
        };
        let rows = 2 * table_count;
        let metadata = json!({"identity":{"document_uid":work.document_id}, "source":{"retrievable":true},
            "file":{"sha256":work.original_sha256,"row_count":rows}, "processing":{"stages":{"sql":"done"}}, "extensions":extensions});
        let mut files = vec![
            ("output.md".to_owned(), b"catalog".to_vec()),
            (
                "metadata.json".to_owned(),
                serde_json::to_vec(&metadata).unwrap(),
            ),
            (
                "tables.json".to_owned(),
                serde_json::to_vec(&tables).unwrap(),
            ),
        ];
        for i in 0..table_count {
            files.push((format!("datasets/{i}.parquet"), b"PAR1".to_vec()));
        }
        let borrowed: Vec<(&str, &[u8])> = files
            .iter()
            .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
            .collect();
        let done = commit_rows(&p, &descriptor, &borrowed, 0, Some(rows)).await;
        assert_eq!(done.status, ProcessingStatus::Succeeded);
        let (generation, manifest) = published(&d.e.pool, work.document_id).await;
        assert_eq!(manifest.vectors, 0);
        assert_eq!(manifest.rows, Some(rows));
        let retrievable: bool = sqlx::query_scalar("select retrievable from document where id=$1")
            .bind(work.document_id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
        assert!(retrievable);
        let (_, listed) = d
            .json("reader", "GET", &attachments(space, session), Value::Null)
            .await;
        let row = listed
            .as_array()
            .unwrap()
            .iter()
            .find(|a| a["document_id"] == work.document_id.to_string())
            .unwrap();
        assert_eq!(row["ready"], true);
        assert_eq!(row["processing"]["vectors"], 0);
        // A succeeded attempt alone does not confer binding eligibility.
        for (retrievable, pending, publication) in [
            (false, false, Some(generation.id)),
            (true, true, Some(generation.id)),
            (true, false, None),
        ] {
            sqlx::query("update document set retrievable=$2, retrieval_id=$5, retrieval_actor='reader', retrieval_target=true, retrieval_phase='ready', retrieval_confirmed=not $3, published_generation=$4 where id=$1")
                .bind(work.document_id).bind(retrievable).bind(pending).bind(publication).bind(Uuid::new_v4())
                .execute(&d.e.pool).await.unwrap();
            let (_, listed) = d
                .json("reader", "GET", &attachments(space, session), Value::Null)
                .await;
            let row = listed
                .as_array()
                .unwrap()
                .iter()
                .find(|a| a["document_id"] == work.document_id.to_string())
                .unwrap();
            assert_eq!(row["processing"]["status"], "succeeded");
            assert_eq!(row["ready"], false);
        }
        sqlx::query("update document set retrievable=true, retrieval_id=null, retrieval_actor=null, retrieval_target=null, retrieval_phase=null, retrieval_confirmed=null, published_generation=$2 where id=$1")
            .bind(work.document_id).bind(generation.id).execute(&d.e.pool).await.unwrap();
        let (code, retired) = json_response(
            d.request(
                "reader",
                "DELETE",
                &format!("{}/{}", attachments(space, session), work.document_id),
                Body::empty(),
                "",
                None,
            )
            .await,
        )
        .await;
        assert_eq!(code, 202, "{retired}");
        let deletion_id = retired["id"].as_str().unwrap().parse().unwrap();
        expire_generations(&d.e.pool, operation).await;
        let candidate = p
            .cleanup_candidates()
            .await
            .unwrap()
            .into_iter()
            .find(|c| c.work.document_id == work.document_id)
            .unwrap();
        assert!(candidate.purge_document);
        let objects = p
            .derived
            .list(&candidate.output_prefix, None, 1000)
            .await
            .unwrap();
        for table in &tables {
            let key = format!(
                "{}{}",
                generation.prefix,
                table["object_key"].as_str().unwrap()
            );
            assert!(objects.objects.iter().any(|(name, _, _)| name == &key));
        }
        for (key, _, _) in objects.objects {
            p.derived.delete(&key).await.unwrap();
        }
        p.cleaned(control_plane::processing::cleanup::Cleaned {
            work: candidate.work,
            generation: candidate.generation,
            cursor: 0,
            next_cursor: 0,
            objects_empty: true,
            purge_document: true,
        })
        .await
        .unwrap();
        cleanup::batch(&d.e.pool, &d.e.fga, deletion_id)
            .await
            .unwrap();
        let remaining: i64 =
            sqlx::query_scalar("select count(*) from artifact where generation_id=$1")
                .bind(generation.id)
                .fetch_one(&d.e.pool)
                .await
                .unwrap();
        assert_eq!(remaining, 0);
        assert!(
            p.derived
                .list(&candidate.output_prefix, None, 1000)
                .await
                .unwrap()
                .objects
                .is_empty()
        );
    }
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn reader_attachment_is_processed_and_published_in_its_conversation() {
    let (d, p) = Box::pin(setup()).await;
    let space = d.folder.space_id;
    let session = conversation(&d, "reader", space).await;
    let (code, receipt) = attach(&d, "reader", space, session, "note.txt", b"private").await;
    assert_eq!(code, 201, "{receipt}");
    let operation = receipt["processing"]["id"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    let work = store::row(&d.e.pool, operation)
        .await
        .unwrap()
        .work(p.installation);
    assert_eq!(work.profile, Profile::Fast);

    for stage in [Stage::Preparation, Stage::Extraction, Stage::Indexing] {
        let descriptor = p
            .claim(claim(&work, stage, Uuid::new_v4(), 1))
            .await
            .unwrap();
        assert_eq!(descriptor.space_id, space);
        assert_eq!(descriptor.session_id, Some(session));
        assert_eq!(descriptor.folder_id, None);
        assert_eq!(descriptor.folder_path, None);
        assert_eq!(descriptor.actor, "reader");
        let wire = serde_json::to_value(&descriptor).unwrap();
        assert_eq!(wire["session_id"], session.to_string());
        assert!(wire["folder_id"].is_null() && wire["folder_path"].is_null());
        match stage {
            Stage::Preparation => {
                commit(&p, &descriptor, &[("policy.json", b"{}")], 0).await;
            }
            Stage::Extraction => {
                commit(&p, &descriptor, &[("output.md", b"private")], 0).await;
            }
            Stage::Indexing => {
                p.plan_vectors(control_plane::processing::cleanup::VectorPlan {
                    work: work.clone(),
                    generation: descriptor.generation,
                    count: 1,
                })
                .await
                .unwrap();
                let done = commit(
                    &p,
                    &descriptor,
                    &[
                        ("output.md", b"private"),
                        ("metadata.json", b"{}"),
                        ("chunks.jsonl", b"{}\n"),
                    ],
                    1,
                )
                .await;
                assert_eq!(done.status, ProcessingStatus::Succeeded);
                assert_eq!(
                    published(&d.e.pool, work.document_id).await.0.id,
                    descriptor.generation
                );
            }
            _ => unreachable!(),
        }
    }
    let (retrievable, command): (bool, Option<Uuid>) =
        sqlx::query_as("select retrievable, retrieval_id from document where id=$1")
            .bind(work.document_id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert!(retrievable);
    assert_eq!(command, None);
    assert!(matches!(
        p.set_retrievable(
            "writer",
            work.document_id,
            control_plane::processing::retrievable::SetRetrievable { retrievable: false },
        )
        .await,
        Err(control_plane::error::AppError::NotFound)
    ));
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn deleted_conversation_refuses_attachment_claim() {
    let (d, p) = Box::pin(setup_with_lifecycle(deletion())).await;
    let space = d.folder.space_id;
    let session = conversation(&d, "reader", space).await;
    let (code, receipt) = attach(&d, "reader", space, session, "note.txt", b"private").await;
    assert_eq!(code, 201, "{receipt}");
    let operation = receipt["processing"]["id"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    let work = store::row(&d.e.pool, operation)
        .await
        .unwrap()
        .work(p.installation);
    assert_eq!(
        status(
            &d,
            "reader",
            "DELETE",
            &format!("/spaces/{space}/sessions/{session}")
        )
        .await,
        202
    );
    assert!(matches!(
        p.claim(claim(&work, Stage::Preparation, Uuid::new_v4(), 1))
            .await,
        Err(control_plane::error::AppError::NotFound)
    ));
    assert!(
        store::generations(&d.e.pool, operation)
            .await
            .unwrap()
            .is_empty()
    );
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
    assert_eq!(listed[0]["ready"], false);

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
    for (user, refused) in [("alice", 404), ("writer", 404), ("owner", 403)] {
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
