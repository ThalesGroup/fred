// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use control_plane::{authorization::Authorization, domain::Permission};
use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;

async fn database(version: Option<i64>) -> PgPool {
    let postgres = std::env::var("CONTROL_PLANE_IT_POSTGRES")
        .expect("needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES");
    let name = format!("t_{}", Uuid::new_v4().simple());
    let admin = PgPool::connect(&format!("{postgres}/postgres"))
        .await
        .unwrap();
    sqlx::query(AssertSqlSafe(format!("create database {name}")))
        .execute(&admin)
        .await
        .unwrap();
    let pool = PgPool::connect(&format!("{postgres}/{name}"))
        .await
        .unwrap();
    let migrator = sqlx::migrate!();
    if let Some(version) = version {
        migrator.run_to(version, &pool).await.unwrap();
    } else {
        migrator.run(&pool).await.unwrap();
    }
    pool
}

fn violation(error: sqlx::Error, code: &str) {
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some(code)
    );
}

async fn spaces(pool: &PgPool) -> [Uuid; 4] {
    let ids = std::array::from_fn(|_| Uuid::new_v4());
    sqlx::query(
        "insert into space(id,kind,name,organization_id,parent_id,personal_owner) values
        ($1,'organization',$1::text,$1,null,null),
        ($2,'team','Team',$1,$1,null),
        ($3,'project','Project',$1,$2,null),
        ($4,'personal','Personal',$1,null,'alice')",
    )
    .bind(ids[0])
    .bind(ids[1])
    .bind(ids[2])
    .bind(ids[3])
    .execute(pool)
    .await
    .unwrap();
    ids
}

async fn invite(pool: &PgPool, space: Uuid) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query(
        "insert into space_invitation(id,space_id,subject,invited_by,expires_at)
        values($1,$2,'alice','owner',now()+interval '2 months')",
    )
    .bind(id)
    .bind(space)
    .execute(pool)
    .await?;
    Ok(id)
}

async fn role(pool: &PgPool, invitation: Uuid, role: &str) -> Result<(), sqlx::Error> {
    sqlx::query("insert into space_invitation_role(invitation_id,role) values($1,$2)")
        .bind(invitation)
        .bind(role)
        .execute(pool)
        .await?;
    Ok(())
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn invitations_target_collective_spaces_and_keep_their_identity() {
    let pool = database(None).await;
    let [org, team, project, personal] = spaces(&pool).await;
    for space in [org, team, project] {
        invite(&pool, space).await.unwrap();
    }
    let foreign = spaces(&pool).await;
    invite(&pool, foreign[1]).await.unwrap();
    violation(invite(&pool, personal).await.unwrap_err(), "23514");
    violation(invite(&pool, Uuid::new_v4()).await.unwrap_err(), "23503");
    let invitation = invite(&pool, team).await.unwrap();
    for statement in [
        "update space_invitation set id=gen_random_uuid() where id=$1",
        "update space_invitation set space_id=$2 where id=$1",
        "update space_invitation set subject='bob' where id=$1",
        "update space_invitation set invited_by='someone-else' where id=$1",
        "update space_invitation set created_at=created_at-interval '1 hour' where id=$1",
    ] {
        let query = sqlx::query(AssertSqlSafe(statement)).bind(invitation);
        let error = if statement.contains("$2") {
            query.bind(personal).execute(&pool).await.unwrap_err()
        } else {
            query.execute(&pool).await.unwrap_err()
        };
        violation(error, "23514");
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn invitation_roles_are_unique_known_and_scoped() {
    let pool = database(None).await;
    let [org, team, project, _] = spaces(&pool).await;
    let organization = invite(&pool, org).await.unwrap();
    role(&pool, organization, "organization_admin")
        .await
        .unwrap();
    for space in [team, project] {
        let invitation = invite(&pool, space).await.unwrap();
        for name in ["member", "editor", "owner", "analyst"] {
            role(&pool, invitation, name).await.unwrap();
        }
        violation(
            role(&pool, invitation, "organization_admin")
                .await
                .unwrap_err(),
            "23514",
        );
        violation(
            role(&pool, invitation, "editor").await.unwrap_err(),
            "23505",
        );
        violation(
            role(&pool, invitation, "platform_admin").await.unwrap_err(),
            "23514",
        );
        violation(sqlx::query("update space_invitation_role set role='organization_admin' where invitation_id=$1 and role='editor'")
            .bind(invitation).execute(&pool).await.unwrap_err(), "23514");
        violation(
            sqlx::query("update space_invitation_role set invitation_id=$1 where invitation_id=$2")
                .bind(invitation)
                .bind(organization)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    violation(
        role(&pool, Uuid::new_v4(), "editor").await.unwrap_err(),
        "23503",
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn invitations_require_finite_expiration_and_complete_revocation_provenance() {
    let pool = database(None).await;
    let [org, _, _, _] = spaces(&pool).await;
    for (created, expires, code) in [
        (Some("2030-01-01"), None, "23502"),
        (Some("2030-01-01"), Some("2030-01-01"), "23514"),
        (Some("2030-01-01"), Some("2029-12-31"), "23514"),
        (Some("2030-01-01"), Some("infinity"), "23514"),
        (Some("-infinity"), Some("2030-02-01"), "23514"),
    ] {
        violation(
            sqlx::query(
                "insert into space_invitation(id,space_id,subject,invited_by,created_at,expires_at)
            values($1,$2,'alice','owner',$3::text::timestamptz,$4::text::timestamptz)",
            )
            .bind(Uuid::new_v4())
            .bind(org)
            .bind(created)
            .bind(expires)
            .execute(&pool)
            .await
            .unwrap_err(),
            code,
        );
    }
    for (subject, author) in [("", "owner"), ("alice", " ")] {
        violation(
            sqlx::query(
                "insert into space_invitation(id,space_id,subject,invited_by,expires_at)
            values($1,$2,$3,$4,now()+interval '1 hour')",
            )
            .bind(Uuid::new_v4())
            .bind(org)
            .bind(subject)
            .bind(author)
            .execute(&pool)
            .await
            .unwrap_err(),
            "23514",
        );
    }
    let invitation = invite(&pool, org).await.unwrap();
    for statement in [
        "update space_invitation set expires_at=null where id=$1",
        "update space_invitation set expires_at=created_at where id=$1",
        "update space_invitation set expires_at='infinity' where id=$1",
        "update space_invitation set revoked_at=now() where id=$1",
        "update space_invitation set revoked_by='owner' where id=$1",
        "update space_invitation set revoked_at=created_at-interval '1 second',revoked_by='owner' where id=$1",
        "update space_invitation set revoked_at='infinity',revoked_by='owner' where id=$1",
        "update space_invitation set revoked_at=now(),revoked_by=' ' where id=$1",
    ] {
        violation(
            sqlx::query(AssertSqlSafe(statement))
                .bind(invitation)
                .execute(&pool)
                .await
                .unwrap_err(),
            if statement.contains("expires_at=null") {
                "23502"
            } else {
                "23514"
            },
        );
    }
    sqlx::query("update space_invitation set revoked_at=now(),revoked_by='owner' where id=$1")
        .bind(invitation)
        .execute(&pool)
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn invitations_are_inert_and_permanent_grants_survive_their_revocation() {
    let pool = database(Some(5)).await;
    let [org, team, project, _] = spaces(&pool).await;
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'alice','member')")
        .bind(org)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    let first = invite(&pool, team).await.unwrap();
    let second = invite(&pool, project).await.unwrap();
    let foreign = spaces(&pool).await;
    let third = invite(&pool, foreign[1]).await.unwrap();
    for invitation in [first, second, third] {
        role(&pool, invitation, "editor").await.unwrap();
    }
    let auth = Authorization::new(pool.clone());
    assert!(auth.check("alice", Permission::Read, org).await.unwrap());
    assert!(!auth.check("alice", Permission::Write, team).await.unwrap());
    assert!(
        !auth
            .check("alice", Permission::Read, foreign[1])
            .await
            .unwrap()
    );
    assert_eq!(
        control_plane::spaces::organization(&pool, "alice")
            .await
            .unwrap(),
        Some(org)
    );
    // The same role can have a permanent grant and a separate invitation origin.
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'alice','editor')")
        .bind(team)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("update space_invitation set revoked_at=now(),revoked_by='owner' where id=$1")
        .bind(first)
        .execute(&pool)
        .await
        .unwrap();
    assert!(auth.check("alice", Permission::Write, team).await.unwrap());
    let other_unrevoked: i64 = sqlx::query_scalar(
        "select count(*) from space_invitation where id=any($1) and revoked_at is null",
    )
    .bind([second, third].as_slice())
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(other_unrevoked, 2);
    sqlx::query("delete from space_invitation where id=$1")
        .bind(first)
        .execute(&pool)
        .await
        .unwrap();
    assert!(auth.check("alice", Permission::Write, team).await.unwrap());
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn space_purge_cascades_its_invitations_and_roles_only() {
    let pool = database(None).await;
    let [_, team, project, _] = spaces(&pool).await;
    let team_invitation = invite(&pool, team).await.unwrap();
    let project_invitation = invite(&pool, project).await.unwrap();
    for invitation in [team_invitation, project_invitation] {
        role(&pool, invitation, "analyst").await.unwrap();
    }
    sqlx::query("delete from space where id=$1")
        .bind(project)
        .execute(&pool)
        .await
        .unwrap();
    let remaining: Vec<Uuid> = sqlx::query_scalar("select id from space_invitation")
        .fetch_all(&pool)
        .await
        .unwrap();
    assert_eq!(remaining, vec![team_invitation]);
    let remaining: Vec<Uuid> =
        sqlx::query_scalar("select invitation_id from space_invitation_role")
            .fetch_all(&pool)
            .await
            .unwrap();
    assert_eq!(remaining, vec![team_invitation]);
}
