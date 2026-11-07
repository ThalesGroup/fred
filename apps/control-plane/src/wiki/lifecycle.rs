// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Wiki cleanup participates in the existing lifecycle sweep and its transactions.
use crate::error::AppResult;
use sqlx::{PgConnection, PgPool};
use uuid::Uuid;

pub(crate) async fn expire(pool: &PgPool, limit: u32) -> AppResult<()> {
    sqlx::query("with due as (select revision_id from wiki_revision where status='proposed'
        and expires_at<=clock_timestamp() order by expires_at,revision_id limit $1 for update skip locked)
        update wiki_revision r set status='rejected' from due where r.revision_id=due.revision_id")
        .bind(i64::from(limit)).execute(pool).await?;
    Ok(())
}

/// Returns true after a bounded batch, asking the existing receipt to resume.
/// A published revision's session_id is attribution, never a cascading owner.
pub(crate) async fn purge(
    conn: &mut PgConnection,
    deletion: Uuid,
    session: Option<Uuid>,
) -> AppResult<bool> {
    if let Some(session) = session {
        return Ok(sqlx::query("delete from wiki_revision where revision_id in (
            select revision_id from wiki_revision where session_id=$1 and status in ('proposed','rejected')
            order by revision_id limit 1000)")
            .bind(session).execute(conn).await?.rows_affected()>0);
    }
    // Detach current pointers first; a retired Wiki is already unreadable. This
    // allows bounded revision deletion even for pages with very long histories.
    if sqlx::query("update wiki_page set current_revision_id=null where page_id in (
        select p.page_id from wiki_page p join space s on s.id=p.space_id
        where s.deletion_id=$1 and p.current_revision_id is not null order by p.page_id limit 1000)")
        .bind(deletion).execute(&mut *conn).await?.rows_affected()>0 { return Ok(true); }
    if sqlx::query(
        "delete from wiki_revision where revision_id in (
        select r.revision_id from wiki_revision r join space s on s.id=r.space_id
        where s.deletion_id=$1 order by r.revision_id limit 1000)",
    )
    .bind(deletion)
    .execute(&mut *conn)
    .await?
    .rows_affected()
        > 0
    {
        return Ok(true);
    }
    Ok(sqlx::query(
        "delete from wiki_page where page_id in (
        select p.page_id from wiki_page p join space s on s.id=p.space_id where s.deletion_id=$1
        and not exists(select 1 from wiki_page child where child.parent_page_id=p.page_id)
        order by p.page_id limit 1000)",
    )
    .bind(deletion)
    .execute(conn)
    .await?
    .rows_affected()
        > 0)
}
