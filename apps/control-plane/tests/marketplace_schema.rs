// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use serde_json::json;
use sqlx::{PgPool, types::Json};
use uuid::Uuid;

#[path = "support/database.rs"]
mod database;

async fn spaces(pool: &PgPool) -> (Uuid, Uuid, Uuid) {
    let (org, source, target) = (Uuid::new_v4(), Uuid::new_v4(), Uuid::new_v4());
    sqlx::query("insert into space(id,kind,name,organization_id,parent_id,personal_owner) values
        ($1,'organization',$1::text,$1,null,null),($2,'personal','Source',$1,null,'alice'),($3,'team','Target',$1,$1,null)")
        .bind(org).bind(source).bind(target).execute(pool).await.unwrap();
    (org, source, target)
}

async fn proposal(pool: &PgPool, org: Uuid, source: Uuid, entry: Uuid, kind: &str) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into marketplace_entry(entry_id,marketplace_space_id,kind) values($1,$2,$3) on conflict do nothing")
        .bind(entry).bind(org).bind(kind).execute(pool).await.unwrap();
    sqlx::query("insert into marketplace_proposal(proposal_id,entry_id,marketplace_space_id,kind,proposing_space_id,origin_name,
        submitted_by,request_key,request_hash,package,package_hash,display_name,description)
        values($1,$2,$3,$4,$5,'Source','alice',$1,$6,$7,$6,'Same name','Frozen')")
        .bind(id).bind(entry).bind(org).bind(kind).bind(source).bind("a".repeat(64))
        .bind(Json(json!({"kind":kind,"content":{"text":"Frozen"}}))).execute(pool).await.unwrap();
    id
}

async fn approve(pool: &PgPool, entry: Uuid, proposal: Uuid) {
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("update marketplace_proposal set state='approved',decided_by='editor',decided_at=clock_timestamp() where proposal_id=$1")
        .bind(proposal).execute(&mut *tx).await.unwrap();
    sqlx::query("update marketplace_entry set published_proposal_id=$2,published_at=clock_timestamp(),publication_version=publication_version+1 where entry_id=$1")
        .bind(entry).bind(proposal).execute(&mut *tx).await.unwrap();
    tx.commit().await.unwrap();
}

fn violation(error: sqlx::Error, code: &str) {
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some(code)
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn marketplace_snapshot_constraints_and_source_deletion_apply_to_all_kinds() {
    let pool = database::database().await;
    let (org, source, _) = spaces(&pool).await;
    let (outside, _, _) = spaces(&pool).await;
    for kind in ["prompt", "skill", "agent"] {
        let entry = Uuid::new_v4();
        let id = proposal(&pool, org, source, entry, kind).await;
        violation(sqlx::query("update marketplace_entry set published_proposal_id=$2,published_at=clock_timestamp(),publication_version=1 where entry_id=$1")
            .bind(entry).bind(id).execute(&pool).await.unwrap_err(),"23503");
        for statement in [
            "update marketplace_proposal set package=package || '{\"changed\":true}' where proposal_id=$1",
            "update marketplace_proposal set package_hash=repeat('b',64) where proposal_id=$1",
            "update marketplace_proposal set submitted_by='editor' where proposal_id=$1",
            "update marketplace_proposal set proposing_space_id=null where proposal_id=$1",
            "update marketplace_proposal set state='approved' where proposal_id=$1",
        ] {
            violation(
                sqlx::query(statement)
                    .bind(id)
                    .execute(&pool)
                    .await
                    .unwrap_err(),
                "23514",
            );
        }
        violation(
            sqlx::query(
                "update marketplace_proposal set marketplace_space_id=$2 where proposal_id=$1",
            )
            .bind(id)
            .bind(outside)
            .execute(&pool)
            .await
            .unwrap_err(),
            "23514",
        );
        approve(&pool, entry, id).await;
        let other_entry = Uuid::new_v4();
        let other = proposal(&pool, org, source, other_entry, kind).await;
        approve(&pool, other_entry, other).await;
        violation(sqlx::query("update marketplace_entry set published_proposal_id=$2,published_at=clock_timestamp(),publication_version=2 where entry_id=$1")
            .bind(entry).bind(other).execute(&pool).await.unwrap_err(),"23503");
        violation(sqlx::query("update marketplace_proposal set state='rejected',decided_by='other' where proposal_id=$1")
            .bind(id).execute(&pool).await.unwrap_err(),"23514");
        // A pending/refused successor does not replace the approved snapshot.
        let successor = proposal(&pool, org, source, entry, kind).await;
        sqlx::query("update marketplace_proposal set state='rejected',decided_by='editor',decided_at=clock_timestamp() where proposal_id=$1")
            .bind(successor).execute(&pool).await.unwrap();
        assert_eq!(
            sqlx::query_scalar::<_, Uuid>(
                "select published_proposal_id from marketplace_entry where entry_id=$1"
            )
            .bind(entry)
            .fetch_one(&pool)
            .await
            .unwrap(),
            id
        );
    }
    // Detaching the proposal's access relation never deletes catalogue content.
    sqlx::query("delete from space where id=$1")
        .bind(source)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from marketplace_entry where published_proposal_id is not null"
        )
        .fetch_one(&pool)
        .await
        .unwrap(),
        6
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from marketplace_proposal where proposing_space_id is null"
        )
        .fetch_one(&pool)
        .await
        .unwrap(),
        9
    );
    sqlx::query("delete from space where organization_id=$1")
        .bind(org)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from marketplace_proposal")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn marketplace_receipts_protect_placement_and_outlive_catalogue_and_resource() {
    let pool = database::database().await;
    let (org, source, target) = spaces(&pool).await;
    let (outside, _, _) = spaces(&pool).await;
    for kind in ["prompt", "skill", "agent"] {
        let entry = Uuid::new_v4();
        let id = proposal(&pool, org, source, entry, kind).await;
        approve(&pool, entry, id).await;
        let resource = Uuid::new_v4();
        match kind {
            "prompt" => {
                sqlx::query("insert into prompt(prompt_id,space_id,logical_name,display_name,text,created_by) values($1,$2,'same','Same','Independent','editor')")
                .bind(resource).bind(target).execute(&pool).await.unwrap();
            }
            "skill" => {
                sqlx::query("insert into skill(skill_id,space_id,name,summary,files,revision,created_by,updated_by) values($1,$2,'same','{\"name\":\"same\"}','{\"SKILL.md\":\"Independent\"}',repeat('a',64),'editor','editor')")
                .bind(resource).bind(target).execute(&pool).await.unwrap();
            }
            _ => {
                sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'native','assistant','Same','{}','editor','same')")
                .bind(resource).bind(target).execute(&pool).await.unwrap();
            }
        }
        let receipt = Uuid::new_v4();
        let insert = || {
            sqlx::query("insert into marketplace_installation(installation_id,actor,request_key,request_hash,entry_id,proposal_id,package_hash,
            kind,space_id,resource_id,live_space_id,prompt_id,skill_id,agent_instance_id)
            values($1,'editor',$1,repeat('a',64),$2,$3,repeat('a',64),$4,$5,$6,$5,$7,$8,$9)")
            .bind(receipt).bind(entry).bind(id).bind(kind).bind(target).bind(resource)
            .bind((kind=="prompt").then_some(resource)).bind((kind=="skill").then_some(resource)).bind((kind=="agent").then_some(resource))
        };
        insert().execute(&pool).await.unwrap();
        violation(insert().execute(&pool).await.unwrap_err(), "23505");
        for statement in [
            "update marketplace_installation set resource_id=$2 where installation_id=$1",
            "update marketplace_installation set live_space_id=$2 where installation_id=$1",
        ] {
            violation(
                sqlx::query(statement)
                    .bind(receipt)
                    .bind(outside)
                    .execute(&pool)
                    .await
                    .unwrap_err(),
                "23514",
            );
        }
        // Catalogue deletion cannot cascade to either the resource or its durable receipt.
        sqlx::query("delete from marketplace_entry where entry_id=$1")
            .bind(entry)
            .execute(&pool)
            .await
            .unwrap();
        let remove = match kind {
            "prompt" => "delete from prompt where prompt_id=$1",
            "skill" => "delete from skill where skill_id=$1",
            _ => "delete from agent_instance where agent_instance_id=$1",
        };
        assert_eq!(
            sqlx::query(remove)
                .bind(resource)
                .execute(&pool)
                .await
                .unwrap()
                .rows_affected(),
            1
        );
        assert_eq!(sqlx::query_scalar::<_,Uuid>("select resource_id from marketplace_installation where installation_id=$1 and coalesce(prompt_id,skill_id,agent_instance_id) is null")
            .bind(receipt).fetch_one(&pool).await.unwrap(),resource);
    }
    sqlx::query("delete from space where id=$1")
        .bind(target)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from marketplace_installation where live_space_id is null"
        )
        .fetch_one(&pool)
        .await
        .unwrap(),
        3
    );
}
