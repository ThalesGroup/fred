// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

fn memory(space: Uuid, agent: Uuid) -> String {
    format!("/spaces/{space}/agent-instances/{agent}/memory")
}

fn bound(agent: Uuid, session: Uuid) -> String {
    format!("person=reader&run=test-run&agent={agent}&session_id={session}")
}

/// Editors manage notes, members read them and undo their own, and a member's own
/// conversation with this instance remembers and forgets through its workload.
#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn agent_memory_rights_and_conversation_binding() {
    let (d, space, session, agent, token) = delegated_outputs(Default::default()).await;
    let base = memory(space, agent);
    let empty = person_json(&d, "reader", "GET", &base, Value::Null).await;
    assert_eq!(empty, (200, json!({"notes": []})));
    let refused = person_json(&d, "reader", "POST", &base, json!({"content":"x"})).await;
    assert_eq!(refused.0, 403, "{refused:?}");
    for content in [json!("   "), json!("a".repeat(501))] {
        let invalid = person_json(&d, "writer", "POST", &base, json!({ "content": content })).await;
        assert_eq!(invalid.0, 422, "{invalid:?}");
    }
    let edited = person_json(
        &d,
        "writer",
        "POST",
        &base,
        json!({"content":"  Answer in French  "}),
    )
    .await;
    assert_eq!(edited.0, 201, "{edited:?}");
    assert_eq!(edited.1["content"], "Answer in French");
    assert_eq!(edited.1["created_by"], "writer");
    assert_eq!(edited.1["created_session_id"], Value::Null);
    let edited_id = edited.1["note_id"].as_str().unwrap().to_owned();

    let delegated = format!("{base}?{}", bound(agent, session));
    let learned = delegated_json(
        &d,
        &token,
        "POST",
        &delegated,
        json!({"content":"Weekly report on Monday"}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(learned.0, 201, "{learned:?}");
    assert_eq!(learned.1["created_by"], "reader");
    assert_eq!(learned.1["created_session_id"], session.to_string());
    let learned_id = learned.1["note_id"].as_str().unwrap().to_owned();
    // A retry or a re-remembered fact returns the active note instead of a duplicate.
    let again = delegated_json(
        &d,
        &token,
        "POST",
        &delegated,
        json!({"content":" Weekly report on Monday "}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(
        (again.0, again.1["note_id"].as_str()),
        (200, Some(learned_id.as_str()))
    );
    let same = person_json(
        &d,
        "writer",
        "POST",
        &base,
        json!({"content":"Weekly report on Monday"}),
    )
    .await;
    assert_eq!(
        (same.0, same.1["note_id"].as_str()),
        (200, Some(learned_id.as_str()))
    );
    let listed = delegated_json(&d, &token, "GET", &delegated, Value::Null, Uuid::new_v4()).await;
    assert_eq!(listed.0, 200, "{listed:?}");
    assert_eq!(listed.1["notes"].as_array().unwrap().len(), 2);
    assert_eq!(listed.1["notes"][0]["note_id"], edited_id.as_str());

    // A plain member may undo only their own note, idempotently.
    let other = person_json(
        &d,
        "reader",
        "DELETE",
        &format!("{base}/{edited_id}"),
        Value::Null,
    )
    .await;
    assert_eq!(other.0, 403, "{other:?}");
    for _ in 0..2 {
        let undone = person_json(
            &d,
            "reader",
            "DELETE",
            &format!("{base}/{learned_id}"),
            Value::Null,
        )
        .await;
        assert_eq!(undone.0, 204, "{undone:?}");
    }
    let missing = person_json(
        &d,
        "writer",
        "DELETE",
        &format!("{base}/{}", Uuid::new_v4()),
        Value::Null,
    )
    .await;
    assert_eq!(missing.0, 404, "{missing:?}");
    // The conversation forgets any note of its instance.
    let forgotten = delegated_json(
        &d,
        &token,
        "DELETE",
        &format!("{base}/{edited_id}?{}", bound(agent, session)),
        Value::Null,
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(forgotten.0, 204, "{forgotten:?}");
    let provenance: (String, Option<Uuid>) = sqlx::query_as(
        "select forgotten_by,forgotten_session_id from agent_memory_note where note_id=$1::uuid",
    )
    .bind(&edited_id)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert_eq!(provenance, ("reader".into(), Some(session)));
    assert_eq!(
        person_json(&d, "writer", "GET", &base, Value::Null).await,
        (200, json!({"notes": []}))
    );
    let history = person_json(
        &d,
        "writer",
        "GET",
        &format!("{base}?include_forgotten=true"),
        Value::Null,
    )
    .await;
    assert_eq!(history.0, 200, "{history:?}");
    let history = history.1["notes"].as_array().unwrap().clone();
    assert_eq!(history.len(), 2);
    assert!(history.iter().all(|note| note["forgotten_at"].is_string()));
    assert_eq!(history[0]["note_id"], edited_id.as_str());

    // The binding names the person's own conversation with this very instance.
    let foreign = conversation(&d, "writer", space).await;
    let foreign_agent: Uuid =
        sqlx::query_scalar("select agent_instance_id from session_metadata where session_id=$1")
            .bind(foreign)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    for path in [
        format!("{base}?person=reader&run=test-run&agent={foreign_agent}&session_id={session}"),
        format!("{base}?{}", bound(agent, foreign)),
        format!(
            "{}?{}",
            memory(space, foreign_agent),
            bound(foreign_agent, session)
        ),
    ] {
        let wrong = delegated_json(
            &d,
            &token,
            "POST",
            &path,
            json!({"content":"Injected"}),
            Uuid::new_v4(),
        )
        .await;
        assert_eq!(wrong.0, 404, "{path}: {wrong:?}");
    }
    let unbound = delegated_json(
        &d,
        &token,
        "POST",
        &format!("{base}?person=reader&run=test-run&agent={agent}"),
        json!({"content":"x"}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(unbound.0, 422, "{unbound:?}");
    let outsider = delegated_json(
        &d,
        &token,
        "GET",
        &format!("{base}?person=stranger&run=test-run&agent={agent}&session_id={session}"),
        Value::Null,
        Uuid::new_v4(),
    )
    .await;
    // Admission owns the person's rights; a conversation they do not own is unknown.
    assert_eq!(outsider.0, 404, "{outsider:?}");
    let human_session = person_json(
        &d,
        "writer",
        "GET",
        &format!("{base}?session_id={session}"),
        Value::Null,
    )
    .await;
    // A person's own call ignores a conversation binding.
    assert_eq!(human_session, (200, json!({"notes": []})));
    assert_eq!(status(&d, "stranger", "GET", &base).await, 403);
    let count: i64 = sqlx::query_scalar("select count(*) from agent_memory_note")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(count, 2);
}

/// The active-note cap holds for both paths; deleting the instance removes its memory.
#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn agent_memory_cap_and_instance_cascade() {
    let (d, space, session, agent, token) = delegated_outputs(Default::default()).await;
    let base = memory(space, agent);
    sqlx::query(
        "insert into agent_memory_note(note_id,space_id,agent_instance_id,content,created_by)
        select gen_random_uuid(),$1,$2,'note '||n,'writer' from generate_series(1,50) n",
    )
    .bind(space)
    .bind(agent)
    .execute(&d.e.pool)
    .await
    .unwrap();
    let full = person_json(&d, "writer", "POST", &base, json!({"content":"One more"})).await;
    assert_eq!(full.0, 409, "{full:?}");
    assert_eq!(full.1["code"], "memory_full");
    let delegated = format!("{base}?{}", bound(agent, session));
    let full = delegated_json(
        &d,
        &token,
        "POST",
        &delegated,
        json!({"content":"One more"}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(
        (full.0, full.1["code"].clone()),
        (409, json!("memory_full"))
    );
    let first = person_json(&d, "writer", "GET", &base, Value::Null).await.1["notes"][0]["note_id"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        person_json(
            &d,
            "writer",
            "DELETE",
            &format!("{base}/{first}"),
            Value::Null
        )
        .await
        .0,
        204
    );
    let added = delegated_json(
        &d,
        &token,
        "POST",
        &delegated,
        json!({"content":"One more"}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(added.0, 201, "{added:?}");
    let removed = status(
        &d,
        "writer",
        "DELETE",
        &format!("/spaces/{space}/agent-instances/{agent}"),
    )
    .await;
    assert!(matches!(removed, 202 | 204), "{removed}");
    let left: i64 = sqlx::query_scalar("select count(*) from agent_memory_note")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(left, 0);
}

/// An edit replaces the note in one step: the replacement keeps the place and the
/// original date of the first version, names what it revises, and the old version
/// moves to history.
#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn agent_memory_edit_keeps_place_and_history() {
    let (d, space, session, agent, token) = delegated_outputs(Default::default()).await;
    let base = memory(space, agent);
    let mut ids = Vec::new();
    for content in ["First", "Second"] {
        let added = person_json(&d, "writer", "POST", &base, json!({ "content": content })).await;
        assert_eq!(added.0, 201, "{added:?}");
        assert_eq!(added.1["revises_note_id"], Value::Null);
        assert_eq!(added.1["origin_created_at"], added.1["created_at"]);
        ids.push(added.1);
    }
    let first_id = ids[0]["note_id"].as_str().unwrap().to_owned();
    let second_id = ids[1]["note_id"].as_str().unwrap().to_owned();

    let refused = person_json(
        &d,
        "reader",
        "PATCH",
        &format!("{base}/{first_id}"),
        json!({"content":"Mine"}),
    )
    .await;
    // A member may edit only their own note.
    assert_eq!(refused.0, 403, "{refused:?}");
    let invalid = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("{base}/{first_id}"),
        json!({"content":"  "}),
    )
    .await;
    assert_eq!(invalid.0, 422, "{invalid:?}");
    // Unchanged trimmed content writes nothing.
    let same = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("{base}/{first_id}"),
        json!({"content":" First "}),
    )
    .await;
    assert_eq!(same, (200, ids[0].clone()));

    let edited = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("{base}/{first_id}"),
        json!({"content":"First, revised"}),
    )
    .await;
    assert_eq!(edited.0, 200, "{edited:?}");
    assert_eq!(edited.1["content"], "First, revised");
    assert_eq!(edited.1["revises_note_id"], first_id.as_str());
    assert_eq!(edited.1["origin_created_at"], ids[0]["origin_created_at"]);
    assert_ne!(edited.1["note_id"], first_id.as_str());
    assert_eq!(edited.1["forgotten_at"], Value::Null);
    let edited_id = edited.1["note_id"].as_str().unwrap().to_owned();

    // The conversation edits through its binding; the chain keeps the first date.
    let delegated = delegated_json(
        &d,
        &token,
        "PATCH",
        &format!("{base}/{edited_id}?{}", bound(agent, session)),
        json!({"content":"First, revised twice"}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(delegated.0, 200, "{delegated:?}");
    assert_eq!(delegated.1["created_by"], "reader");
    assert_eq!(delegated.1["created_session_id"], session.to_string());
    assert_eq!(delegated.1["revises_note_id"], edited_id.as_str());
    assert_eq!(
        delegated.1["origin_created_at"],
        ids[0]["origin_created_at"]
    );
    let latest_id = delegated.1["note_id"].as_str().unwrap().to_owned();

    let listed = person_json(&d, "writer", "GET", &base, Value::Null).await;
    assert_eq!(listed.0, 200, "{listed:?}");
    let active: Vec<_> = listed.1["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|note| note["note_id"].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(active, [latest_id.clone(), second_id.clone()]);

    let history = person_json(
        &d,
        "writer",
        "GET",
        &format!("{base}?include_forgotten=true"),
        Value::Null,
    )
    .await;
    let history: Vec<_> = history.1["notes"].as_array().unwrap()[2..].to_vec();
    assert_eq!(history.len(), 2);
    assert_eq!(history[0]["note_id"], edited_id.as_str());
    assert_eq!(history[0]["forgotten_by"], "reader");
    assert_eq!(history[1]["note_id"], first_id.as_str());
    assert_eq!(history[1]["forgotten_by"], "writer");
    let provenance: Option<Uuid> = sqlx::query_scalar(
        "select forgotten_session_id from agent_memory_note where note_id=$1::uuid",
    )
    .bind(&edited_id)
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert_eq!(provenance, Some(session));

    // A replaced or forgotten note cannot be edited again; an unknown one is not found.
    let stale = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("{base}/{first_id}"),
        json!({"content":"Stale"}),
    )
    .await;
    assert_eq!(
        (stale.0, stale.1["code"].clone()),
        (409, json!("memory_note_forgotten"))
    );
    let missing = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("{base}/{}", Uuid::new_v4()),
        json!({"content":"Ghost"}),
    )
    .await;
    assert_eq!(missing.0, 404, "{missing:?}");
    let count: i64 = sqlx::query_scalar("select count(*) from agent_memory_note")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(count, 4);
    // The reader wrote the latest version through the conversation: they may correct it.
    let own = person_json(
        &d,
        "reader",
        "PATCH",
        &format!("{base}/{latest_id}"),
        json!({"content":"First, revised by me"}),
    )
    .await;
    assert_eq!(own.0, 200, "{own:?}");
    assert_eq!(own.1["created_by"], "reader");
    assert_eq!(own.1["created_session_id"], Value::Null);
    assert_eq!(own.1["revises_note_id"], latest_id.as_str());

    // Revisions go with the instance.
    let removed = status(
        &d,
        "writer",
        "DELETE",
        &format!("/spaces/{space}/agent-instances/{agent}"),
    )
    .await;
    assert!(matches!(removed, 202 | 204), "{removed}");
    let left: i64 = sqlx::query_scalar("select count(*) from agent_memory_note")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(left, 0);
}
