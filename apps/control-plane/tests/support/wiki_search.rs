// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

async fn create(d: &Documents, space: Uuid, title: &str, text: &str) -> Value {
    let result = person_json(
        d,
        "writer",
        "POST",
        &format!("/spaces/{space}/wiki/pages"),
        json!({"title":title,"content_md":text}),
    )
    .await;
    assert_eq!(result.0, 201, "{result:?}");
    result.1
}

async fn search(d: &Documents, space: Uuid, params: &str) -> Value {
    let result = person_json(
        d,
        "reader",
        "GET",
        &format!("/spaces/{space}/wiki/search?{params}"),
        Value::Null,
    )
    .await;
    assert_eq!(result.0, 200, "{result:?}");
    result.1
}

async fn projection(pool: &sqlx::PgPool) -> Vec<Value> {
    sqlx::query_scalar("select to_jsonb(i) from wiki_page_index i order by page_id")
        .fetch_all(pool)
        .await
        .unwrap()
}

pub(super) async fn rebuilt(pool: &sqlx::PgPool) {
    let before = projection(pool).await;
    sqlx::query("delete from wiki_page_index")
        .execute(pool)
        .await
        .unwrap();
    control_plane::wiki::reconcile(pool).await.unwrap();
    assert_eq!(projection(pool).await, before);
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_publication_rebuild_filters_and_authority() {
    let (d, space, session, agent, token) = delegated_outputs(Default::default()).await;
    enable_wiki(&d, space).await;
    let a = create(&d, space, "Restart service", "---\ntype: procedure\ndescription: Operations\ntags: [ops, local]\nx-fred-aliases: [boot]\nx-fred-read-when: Failure\n---\nRedémarrages et restarting.").await;
    let id = a["page"]["page_id"].as_str().unwrap();
    let b = create(&d, space, "Secondary", "restart service").await;
    assert_eq!(
        search(&d, space, "q=restart").await["hits"][0]["page_id"],
        id
    );
    for term in ["red%C3%A9marrage", "restart", "boot", "failure"] {
        assert_eq!(
            search(&d, space, &format!("q={term}&type=procedure&tag=ops")).await["hits"][0]["page_id"],
            id
        );
    }
    assert_eq!(
        search(&d, space, "q=restart&type=topic").await["hits"],
        json!([])
    );
    assert_eq!(
        search(&d, space, "q=restart&tag=OPS").await["hits"],
        json!([])
    );
    let base = format!("/spaces/{space}/wiki");
    let written = person_json(
        &d,
        "writer",
        "PUT",
        &format!("{base}/pages/{id}/content"),
        json!({"content_md":"Replacement content","base_revision_id":a["revision_id"]}),
    )
    .await;
    assert_eq!(written.0, 200, "{written:?}");
    assert_eq!(
        search(&d, space, "q=replacement").await["hits"][0]["page_id"],
        id
    );
    let restored = person_json(
        &d,
        "writer",
        "POST",
        &format!(
            "{base}/pages/{id}/revisions/{}/restore",
            a["revision_id"].as_str().unwrap()
        ),
        Value::Null,
    )
    .await;
    assert_eq!(restored.0, 200, "{restored:?}");
    let moved = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("{base}/pages/{id}"),
        json!({"title":"Recovery","parent_page_id":b["page"]["page_id"]}),
    )
    .await;
    assert_eq!(moved.0, 200, "{moved:?}");
    assert_eq!(
        search(&d, space, "q=recovery").await["hits"][0]["title"],
        "Recovery"
    );
    let pending = person_json(
        &d,
        "reader",
        "POST",
        &format!("{base}/proposals/page"),
        json!({"title":"Proposal","content_md":"arbitrationneedle"}),
    )
    .await;
    assert_eq!(pending.0, 201, "{pending:?}");
    assert_eq!(
        search(&d, space, "q=arbitrationneedle").await["hits"],
        json!([])
    );
    let accepted = person_json(
        &d,
        "writer",
        "POST",
        &format!(
            "{base}/proposals/{}/accept",
            pending.1["proposal_id"].as_str().unwrap()
        ),
        Value::Null,
    )
    .await;
    assert_eq!(accepted.0, 200, "{accepted:?}");
    assert_eq!(
        search(&d, space, "q=arbitrationneedle").await["hits"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        person_json(
            &d,
            "writer",
            "PUT",
            &format!("{base}/rules"),
            json!({"content_md":"rulesneedle"})
        )
        .await
        .0,
        200
    );
    assert_eq!(search(&d, space, "q=rulesneedle").await["hits"], json!([]));
    let denied = person_json(
        &d,
        "stranger",
        "GET",
        &format!("{base}/search?q=recovery"),
        Value::Null,
    )
    .await;
    assert!(matches!(denied.0, 403 | 404), "{denied:?}");
    let response = d.app.clone().oneshot(Request::builder().uri(format!("/v1{base}/search?q=recovery&person=reader&run=test-run&agent={agent}&session_id={session}"))
        .header("authorization",format!("Bearer {token}")).body(Body::empty()).unwrap()).await.unwrap();
    let delegated = json_response(response).await;
    assert_eq!(delegated.0, 200, "{delegated:?}");
    assert_eq!(delegated.1["hits"][0]["page_id"], id);
    let draft = delegated_json(
        &d,
        &token,
        "POST",
        &format!(
            "{base}/proposals/page?person=reader&run=test-run&agent={agent}&session_id={session}"
        ),
        json!({"title":"Draft","content_md":"---\ntype: topic\n---\ndraftneedle"}),
        Uuid::new_v4(),
    )
    .await;
    assert_eq!(draft.0, 201, "{draft:?}");
    assert_eq!(draft.1["status"], "draft");
    assert_eq!(search(&d, space, "q=draftneedle").await["hits"], json!([]));
    let other = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id,parent_id)
        select $1,'team',$1::text,organization_id,organization_id from space where id=$2",
    )
    .bind(other)
    .bind(space)
    .execute(&d.e.pool)
    .await
    .unwrap();
    seed(&d.e.pool, other, 1).await;
    control_plane::wiki::reconcile(&d.e.pool).await.unwrap();
    let other_id: Uuid = sqlx::query_scalar("select page_id from wiki_page where space_id=$1")
        .bind(other)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(
        search(&d, space, "q=restart").await["hits"]
            .as_array()
            .unwrap()
            .iter()
            .all(|hit| hit["page_id"] != other_id.to_string())
    );
    let denied = person_json(
        &d,
        "reader",
        "GET",
        &format!("/spaces/{other}/wiki/search?q=restart"),
        Value::Null,
    )
    .await;
    assert_eq!(denied.0, 403, "{denied:?}");
    rebuilt(&d.e.pool).await;
    assert_eq!(
        person_json(
            &d,
            "writer",
            "DELETE",
            &format!("{base}/pages/{id}"),
            Value::Null
        )
        .await
        .0,
        204
    );
    assert_eq!(search(&d, space, "q=recovery").await["hits"], json!([]));
    rebuilt(&d.e.pool).await;
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_bounds_stale_candidates_and_pagination() {
    let (d, space, _, _, _) = delegated_outputs(Default::default()).await;
    enable_wiki(&d, space).await;
    for (params, field) in [
        ("", "q"),
        ("q=%20", "q"),
        ("q=needle&limit=0", "limit"),
        ("q=needle&limit=21", "limit"),
        ("q=needle&limit=abc", "limit"),
        ("q=needle&offset=-1", "offset"),
        ("q=needle&offset=201", "offset"),
        ("q=needle&type=bogus", "type"),
    ] {
        let result = person_json(
            &d,
            "reader",
            "GET",
            &format!("/spaces/{space}/wiki/search?{params}"),
            Value::Null,
        )
        .await;
        assert_eq!(result.0, 422, "{result:?}");
        assert_eq!(result.1["code"], "invalid_fields");
        assert!(
            result.1["detail"].as_str().unwrap().starts_with(field),
            "{result:?}"
        );
    }
    let oversized = format!("/spaces/{space}/wiki/search?q={}", "a".repeat(201));
    assert_eq!(
        person_json(&d, "reader", "GET", &oversized, Value::Null)
            .await
            .0,
        422
    );
    // Unicode characters, not UTF-8 bytes; tags retain exact-match semantics.
    for (length, expected) in [(100, 200), (101, 422)] {
        let mut url = reqwest::Url::parse("http://fixture/").unwrap();
        url.query_pairs_mut()
            .append_pair("q", "needle")
            .append_pair("tag", &"é".repeat(length));
        let params = url.query().unwrap();
        let result = person_json(
            &d,
            "reader",
            "GET",
            &format!("/spaces/{space}/wiki/search?{params}"),
            Value::Null,
        )
        .await;
        assert_eq!(result.0, expected, "{result:?}");
        if expected == 422 {
            assert_eq!(result.1["code"], "invalid_fields");
            assert!(result.1["detail"].as_str().unwrap().starts_with("tag:"));
        }
    }
    seed(&d.e.pool, space, 205).await;
    control_plane::wiki::reconcile(&d.e.pool).await.unwrap();
    let ids: Vec<Uuid> = sqlx::query_scalar(
        "select page_id from wiki_page_index where space_id=$1 order by page_id",
    )
    .bind(space)
    .fetch_all(&d.e.pool)
    .await
    .unwrap();
    sqlx::query("update wiki_page_index set revision_id=$2 where page_id=any($1)")
        .bind(&ids[..5])
        .bind(Uuid::new_v4())
        .execute(&d.e.pool)
        .await
        .unwrap();
    let first = search(&d, space, "q=needle&limit=2").await;
    assert_eq!(first["hits"].as_array().unwrap().len(), 1);
    assert_eq!(first["next_offset"], 6);
    let mut offset = 0;
    let mut found = Vec::new();
    loop {
        let result = search(&d, space, &format!("q=needle&limit=2&offset={offset}")).await;
        found.extend(
            result["hits"]
                .as_array()
                .unwrap()
                .iter()
                .map(|h| h["page_id"].as_str().unwrap().parse::<Uuid>().unwrap()),
        );
        if let Some(next) = result["next_offset"].as_u64() {
            assert!(next > offset);
            offset = next;
        } else {
            assert_eq!(result["truncated"], true);
            break;
        }
    }
    assert_eq!(found, ids[5..200]);
    let end = search(&d, space, "q=needle&offset=200").await;
    assert_eq!(end["hits"], json!([]));
    assert_eq!(end["truncated"], true);
    // A confirmed read cannot accidentally return a page from another space.
    let foreign = Uuid::new_v4();
    let result = person_json(
        &d,
        "reader",
        "GET",
        &format!("/spaces/{foreign}/wiki/search?q=needle"),
        Value::Null,
    )
    .await;
    assert!(matches!(result.0, 403 | 404), "{result:?}");
    sqlx::query("delete from wiki_page where page_id=any($1)")
        .bind(&ids[10..])
        .execute(&d.e.pool)
        .await
        .unwrap();
    control_plane::wiki::reconcile(&d.e.pool).await.unwrap();
    let mut actual = Vec::new();
    let mut offset = 0;
    loop {
        let result = search(&d, space, &format!("q=needle&limit=2&offset={offset}")).await;
        actual.extend(
            result["hits"]
                .as_array()
                .unwrap()
                .iter()
                .map(|h| h["page_id"].as_str().unwrap().parse::<Uuid>().unwrap()),
        );
        assert_eq!(result["truncated"], false);
        if let Some(next) = result["next_offset"].as_u64() {
            offset = next;
        } else {
            break;
        }
    }
    assert_eq!(actual, ids[..10]);
}

async fn seed(pool: &sqlx::PgPool, space: Uuid, count: i32) {
    let mut tx = pool.begin().await.unwrap();
    let ids: Vec<Uuid> = (0..count).map(|_| Uuid::new_v4()).collect();
    sqlx::query(
        "insert into wiki_page(page_id,space_id,slug,title,updated_by)
        select id,$1,id::text,id::text,'writer' from unnest($2::uuid[]) id",
    )
    .bind(space)
    .bind(&ids)
    .execute(&mut *tx)
    .await
    .unwrap();
    sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,entry_kind,content_md,status,author_user_id)
        select id,$1,id,'page','needle restart redémarrages','published','writer' from unnest($2::uuid[]) id")
        .bind(space).bind(&ids).execute(&mut *tx).await.unwrap();
    sqlx::query("update wiki_page set current_revision_id=page_id where page_id=any($1)")
        .bind(&ids)
        .execute(&mut *tx)
        .await
        .unwrap();
    tx.commit().await.unwrap();
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_atomicity_raw_text_and_versions() {
    let (d, space, _, _, _) = delegated_outputs(Default::default()).await;
    enable_wiki(&d, space).await;
    let a = create(&d, space, "Original", "original text").await;
    let id: Uuid = a["page"]["page_id"].as_str().unwrap().parse().unwrap();
    sqlx::query(
        "alter table wiki_page_index add constraint fixture_failure check(title<>'Rejected')",
    )
    .execute(&d.e.pool)
    .await
    .unwrap();
    let failed = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("/spaces/{space}/wiki/pages/{id}"),
        json!({"title":"Rejected"}),
    )
    .await;
    assert_ne!(failed.0, 200);
    let title: String = sqlx::query_scalar("select title from wiki_page where page_id=$1")
        .bind(id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(title, "Original");
    sqlx::query("alter table wiki_page_index drop constraint fixture_failure")
        .execute(&d.e.pool)
        .await
        .unwrap();
    sqlx::query(
        "alter table wiki_page_index add constraint fixture_failure check(body<>'failure')",
    )
    .execute(&d.e.pool)
    .await
    .unwrap();
    let failed = person_json(
        &d,
        "writer",
        "PUT",
        &format!("/spaces/{space}/wiki/pages/{id}/content"),
        json!({"content_md":"failure","base_revision_id":a["revision_id"]}),
    )
    .await;
    assert_ne!(failed.0, 200);
    let revision: Uuid =
        sqlx::query_scalar("select current_revision_id from wiki_page where page_id=$1")
            .bind(id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(revision.to_string(), a["revision_id"].as_str().unwrap());
    sqlx::query("alter table wiki_page_index drop constraint fixture_failure")
        .execute(&d.e.pool)
        .await
        .unwrap();
    let raw = "---\nstatus: null\n---\nrawneedle";
    let revision = Uuid::new_v4();
    sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,entry_kind,content_md,status,author_user_id) values($1,$2,$3,'page',$4,'published','writer')")
        .bind(revision).bind(space).bind(id).bind(raw).execute(&d.e.pool).await.unwrap();
    sqlx::query("update wiki_page set current_revision_id=$2 where page_id=$1")
        .bind(id)
        .bind(revision)
        .execute(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(search(&d, space, "q=original").await["hits"], json!([]));
    control_plane::wiki::reconcile(&d.e.pool).await.unwrap();
    let result = search(&d, space, "q=rawneedle").await;
    assert_eq!(result["hits"][0]["page_type"], "untyped");
    let stored: String = sqlx::query_scalar("select body from wiki_page_index where page_id=$1")
        .bind(id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(stored, raw);
    sqlx::query("update wiki_page_index set index_version=2 where page_id=$1")
        .bind(id)
        .execute(&d.e.pool)
        .await
        .unwrap();
    let renamed = person_json(
        &d,
        "writer",
        "PATCH",
        &format!("/spaces/{space}/wiki/pages/{id}"),
        json!({"title":"Changed"}),
    )
    .await;
    assert_eq!(renamed.0, 200, "{renamed:?}");
    let state: (i32, String) =
        sqlx::query_as("select index_version,title from wiki_page_index where page_id=$1")
            .bind(id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(state, (2, "Original".into()));
    assert!(
        tokio::time::timeout(
            Duration::from_secs(2),
            control_plane::wiki::reconcile(&d.e.pool)
        )
        .await
        .unwrap()
        .is_ok()
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_contextual_excerpts_keep_stemming_and_text_bounds() {
    let (d, space, _, _, _) = delegated_outputs(Default::default()).await;
    enable_wiki(&d, space).await;
    for (word, query) in [
        ("redémarrages", "red%C3%A9marrage"),
        ("restarting", "restart"),
    ] {
        let text = format!(
            "{} <span>{word}</span> {}",
            "introduction ".repeat(100),
            "été ".repeat(100)
        );
        create(&d, space, query, &text).await;
        let result = search(&d, space, &format!("q={query}")).await;
        let excerpt = result["hits"][0]["excerpt"].as_str().unwrap();
        assert!(excerpt.contains(word), "{excerpt:?}");
        assert!(excerpt.chars().count() <= 300);
        assert!(!excerpt.contains("<b>"));
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_reconcile_serializes_publication_deletion_and_replicas() {
    for delete in [false, true] {
        let (d, space, _, _, _) = delegated_outputs(Default::default()).await;
        enable_wiki(&d, space).await;
        let a = create(&d, space, "Concurrent", "oldneedle").await;
        let id = a["page"]["page_id"].as_str().unwrap().to_owned();
        seed(&d.e.pool, space, 105).await;
        sqlx::query("delete from wiki_page_index")
            .execute(&d.e.pool)
            .await
            .unwrap();
        // Pause the first projection after it owns the space lock. This models
        // a slow batch without sleep-based ordering of mutation/reconciliation.
        sqlx::raw_sql(
            "create function fixture_index_gate() returns trigger language plpgsql as $$ begin
            perform pg_advisory_xact_lock(782399); return new; end $$;
            create trigger fixture_index_gate before insert on wiki_page_index
            for each row execute function fixture_index_gate();",
        )
        .execute(&d.e.pool)
        .await
        .unwrap();
        let mut gate = d.e.pool.begin().await.unwrap();
        let blocker: i32 =
            sqlx::query_scalar("select pg_backend_pid() from pg_advisory_xact_lock(782399)")
                .fetch_one(&mut *gate)
                .await
                .unwrap();
        let pool = d.e.pool.clone();
        let reconcile = tokio::spawn(async move { control_plane::wiki::reconcile(&pool).await });
        let reconciler = wiki_waiter(&d.e.pool, blocker, "insert into wiki_page_index%").await;
        let pool = d.e.pool.clone();
        let mut second = tokio::spawn(async move { control_plane::wiki::reconcile(&pool).await });
        assert!(
            tokio::time::timeout(Duration::from_millis(120), &mut second)
                .await
                .is_err(),
            "SKIP LOCKED cannot establish exhaustion"
        );
        let d = Arc::new(d);
        let mutation = {
            let d = d.clone();
            let id = id.clone();
            tokio::spawn(async move {
                if delete {
                    person_json(
                        &d,
                        "writer",
                        "DELETE",
                        &format!("/spaces/{space}/wiki/pages/{id}"),
                        Value::Null,
                    )
                    .await
                } else {
                    person_json(
                        &d,
                        "writer",
                        "PUT",
                        &format!("/spaces/{space}/wiki/pages/{id}/content"),
                        json!({"content_md":"newneedle","base_revision_id":a["revision_id"]}),
                    )
                    .await
                }
            })
        };
        wiki_waiter(
            &d.e.pool,
            reconciler,
            "select id from space where id=$1 for no key update%",
        )
        .await;
        gate.commit().await.unwrap();
        let result = tokio::time::timeout(Duration::from_secs(5), mutation)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(result.0, if delete { 204 } else { 200 }, "{result:?}");
        tokio::time::timeout(Duration::from_secs(10), reconcile)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        tokio::time::timeout(Duration::from_secs(10), second)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        let revisions:Vec<(Uuid,Uuid)>=sqlx::query_as("select i.revision_id,p.current_revision_id from wiki_page_index i join wiki_page p using(page_id)")
            .fetch_all(&d.e.pool).await.unwrap();
        assert!(
            revisions
                .iter()
                .all(|(indexed, current)| indexed == current)
        );
        assert_eq!(search(&d, space, "q=oldneedle").await["hits"], json!([]));
        assert_eq!(
            search(&d, space, "q=newneedle").await["hits"]
                .as_array()
                .unwrap()
                .len(),
            if delete { 0 } else { 1 }
        );
        rebuilt(&d.e.pool).await;
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_initialize_schema_and_startup_catch_up() {
    let (d, space, _, _, _) = delegated_outputs(Default::default()).await;
    enable_wiki(&d, space).await;
    seed(&d.e.pool, space, 2).await;
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let mut url =
        reqwest::Url::parse(&std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap()).unwrap();
    url.set_username("fred_cp").unwrap();
    url.set_password(Some("it")).unwrap();
    url.set_path(&database);
    let status = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("initialize-schema")
        .env("DATABASE_URL", url.as_str())
        .output()
        .await
        .unwrap();
    assert!(
        status.status.success(),
        "{}",
        String::from_utf8_lossy(&status.stderr)
    );
    assert_eq!(projection(&d.e.pool).await.len(), 2);
    sqlx::query("update wiki_page_index set index_version=2")
        .execute(&d.e.pool)
        .await
        .unwrap();
    let future = tokio::time::timeout(
        Duration::from_secs(5),
        tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
            .arg("initialize-schema")
            .env("DATABASE_URL", url.as_str())
            .output(),
    )
    .await
    .unwrap()
    .unwrap();
    assert!(
        future.status.success(),
        "{}",
        String::from_utf8_lossy(&future.stderr)
    );
    assert_eq!(projection(&d.e.pool).await[0]["index_version"], 2);
    sqlx::query("update wiki_page_index set index_version=1")
        .execute(&d.e.pool)
        .await
        .unwrap();
    seed(&d.e.pool, space, 1).await;
    // The shared reconcile pass catches a publication without projection.
    control_plane::wiki::reconcile(&d.e.pool).await.unwrap();
    assert_eq!(
        search(&d, space, "q=needle").await["hits"]
            .as_array()
            .unwrap()
            .len(),
        3
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres and S3"]
async fn wiki_search_startup_failure_keeps_http_alive_retries_and_stops() {
    let e = crate::env().await;
    let (_, team) = crate::org_and_team(&e).await;
    let space = team.id;
    seed(&e.pool, space, 1).await;
    // Sequence increments survive the failed transaction and reveal real attempts.
    sqlx::raw_sql(
        "create sequence fixture_wiki_attempts;
        create function fixture_wiki_failure() returns trigger language plpgsql as $$ begin
            perform nextval('fixture_wiki_attempts'); raise exception 'fixture'; end $$;
        create trigger fixture_wiki_failure before insert on wiki_page_index
            for each row execute function fixture_wiki_failure();",
    )
    .execute(&e.pool)
    .await
    .unwrap();
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let url = reqwest::Url::parse(&std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap()).unwrap();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    drop(listener);
    let config = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(config.path(), serde_json::to_vec(&json!({
        "app": {"base_url":"/v1", "address":"127.0.0.1", "port":port},
        "security": {"user":{"enabled":false,"realm_url":"http://fixture/realms/app","client_id":"app"}},
        "storage": {"postgres":{"host":url.host_str().unwrap(),"port":url.port().unwrap(),"database":database,"username":"fred_cp"}},
        "scheduler": {"lifecycle":{"enabled":false,"temporal":{"host":"127.0.0.1:1","connect_timeout_seconds":1}}}
    })).unwrap()).unwrap();
    let logs = tempfile::NamedTempFile::new().unwrap();
    let mut server = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("serve")
        .env_clear()
        .env("CONFIG_FILE", config.path())
        .env("ENV_FILE", "/nonexistent-fixture-env")
        .env("FRED_POSTGRES_PASSWORD", "it")
        .stdout(logs.reopen().unwrap())
        .stderr(logs.reopen().unwrap())
        .kill_on_drop(true)
        .spawn()
        .unwrap();
    let client = reqwest::Client::new();
    let health = format!("http://127.0.0.1:{port}/v1/healthz");
    tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            assert!(
                server.try_wait().unwrap().is_none(),
                "{}",
                std::fs::read_to_string(logs.path()).unwrap()
            );
            let tried: bool = sqlx::query_scalar("select is_called from fixture_wiki_attempts")
                .fetch_one(&e.pool)
                .await
                .unwrap();
            if tried
                && client
                    .get(&health)
                    .send()
                    .await
                    .is_ok_and(|r| r.status().is_success())
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
    })
    .await
    .unwrap();
    tokio::time::sleep(Duration::from_secs(1)).await;
    let attempts: i64 = sqlx::query_scalar("select last_value from fixture_wiki_attempts")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(attempts, 1, "retry must be spaced, not a busy loop");
    assert!(server.try_wait().unwrap().is_none());
    assert!(
        client
            .get(&health)
            .send()
            .await
            .unwrap()
            .status()
            .is_success()
    );
    sqlx::query("drop trigger fixture_wiki_failure on wiki_page_index")
        .execute(&e.pool)
        .await
        .unwrap();
    tokio::time::timeout(Duration::from_secs(8), async {
        while projection(&e.pool).await.is_empty() {
            assert!(server.try_wait().unwrap().is_none());
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    })
    .await
    .unwrap();
    assert!(
        client
            .get(&health)
            .send()
            .await
            .unwrap()
            .status()
            .is_success()
    );
    assert!(
        std::fs::read_to_string(logs.path())
            .unwrap()
            .contains("wiki_index_retry")
    );
    assert!(
        tokio::process::Command::new("kill")
            .args(["-TERM", &server.id().unwrap().to_string()])
            .status()
            .await
            .unwrap()
            .success()
    );
    assert!(
        tokio::time::timeout(Duration::from_secs(5), server.wait())
            .await
            .unwrap()
            .unwrap()
            .success()
    );

    // Shutdown also interrupts the retry delay, not only the completed pass.
    use futures::FutureExt;
    let (stop, mut stopped) = tokio::sync::watch::channel(());
    let stopping = async move {
        let _ = stopped.changed().await;
    }
    .shared();
    let pool = e.pool.clone();
    pool.close().await;
    let startup = tokio::spawn(async move { control_plane::wiki::startup(&pool, stopping).await });
    tokio::time::sleep(Duration::from_millis(25)).await;
    assert!(!startup.is_finished());
    stop.send(()).unwrap();
    tokio::time::timeout(Duration::from_millis(500), startup)
        .await
        .unwrap()
        .unwrap();
}
