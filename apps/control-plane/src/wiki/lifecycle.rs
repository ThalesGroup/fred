// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Wiki cleanup participates in the existing lifecycle sweep and its transactions.
use crate::error::AppResult;
use sqlx::PgConnection;
use uuid::Uuid;

/// Returns true after a bounded batch, asking the existing receipt to resume.
/// Drafts go with their conversation (cascade); this purges a retired space's Wiki.
pub(crate) async fn purge(conn: &mut PgConnection, deletion: Uuid) -> AppResult<bool> {
    // Detach page pointers first; a retired Wiki is already unreadable. This allows
    // bounded revision deletion even for long histories. A file entry keeps its only
    // revision (`wiki_file_current`): leaf deletion removes both by cascade.
    if sqlx::query(
        "update wiki_page set current_revision_id=null where page_id in (
        select p.page_id from wiki_page p join space s on s.id=p.space_id
        where s.deletion_id=$1 and p.current_revision_id is not null and p.kind<>'file'
        order by p.page_id limit 1000)",
    )
    .bind(deletion)
    .execute(&mut *conn)
    .await?
    .rows_affected()
        > 0
    {
        return Ok(true);
    }
    if sqlx::query(
        "delete from wiki_revision where revision_id in (
        select r.revision_id from wiki_revision r join space s on s.id=r.space_id
        where s.deletion_id=$1 and not (r.entry_kind='file' and r.page_id is not null)
        order by r.revision_id limit 1000)",
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
