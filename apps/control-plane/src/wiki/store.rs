// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{access::Access, *};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use chrono::{DateTime, Utc};
use sqlx::PgConnection;
use uuid::Uuid;

/// A file entry's bytes are its current revision's Wiki copy.
macro_rules! page_select {
    () => {
        "select p.*,c.mime,c.size,p.current_revision_id as revision_id,coalesce(r.content_md,'') as content_md,
         r.agent_name,r.agent_instance_id,r.author_user_id,exists(select 1 from document_content v where v.source_content_id=c.id
         and v.published_at is not null and v.cleaned_at is null) as has_preview from wiki_page p
         left join wiki_revision r on r.revision_id=p.current_revision_id
         left join document d on d.id=r.document_id left join document_content c on c.id=d.current_content_id"
    };
}

/// `status` and `outdated` are computed from the row and its entry, never stored.
macro_rules! proposal_select {
    () => {
        "select r.revision_id as proposal_id,
         case when r.entry_kind='file' then 'file' when r.page_id is null then 'page' else 'edit' end as kind,
         case when r.status<>'proposed' then 'published' when r.session_id is null then 'pending' else 'draft' end as status,
         coalesce(p.title,r.proposed_title,'') as title,p.slug,pp.slug as parent_slug,r.base_revision_id,r.content_md,
         coalesce(cur.content_md,'') as current_content_md,
         r.status='proposed' and case when r.page_id is not null then p.current_revision_id is distinct from r.base_revision_id
            else exists(select 1 from wiki_page s where s.space_id=r.space_id and s.parent_page_id is not distinct from
            r.proposed_parent_page_id and wiki_title_key(s.title)=wiki_title_key(r.proposed_title)) end as outdated,
         r.created_at,r.author_user_id,r.agent_instance_id,r.agent_name,c.mime,c.size,
         exists(select 1 from document_content v where v.source_content_id=c.id and v.published_at is not null
            and v.cleaned_at is null) as has_preview
         from wiki_revision r left join wiki_page p on p.page_id=r.page_id
         left join wiki_revision cur on cur.revision_id=p.current_revision_id
         left join wiki_page pp on pp.page_id=case when r.status='proposed'
            then r.proposed_parent_page_id else p.parent_page_id end
         left join document d on d.id=r.document_id left join document_content c on c.id=d.current_content_id"
    };
}

/// Arbitration facts; the conversation binding stays internal (D26).
#[derive(sqlx::FromRow)]
pub(super) struct ProposalRow {
    pub status: String,
    pub entry_kind: String,
    pub page_id: Option<Uuid>,
    pub base_revision_id: Option<Uuid>,
    pub session_id: Option<Uuid>,
    pub author_user_id: String,
    pub proposed_title: Option<String>,
    pub proposed_parent_page_id: Option<Uuid>,
    pub content_md: String,
    pub agent_instance_id: Option<Uuid>,
}

pub(super) async fn page(conn: &mut PgConnection, space: Uuid, id: Uuid) -> Result<WikiPageDetail> {
    Ok(sqlx::query_as(concat!(
        page_select!(),
        " where p.space_id=$1 and p.page_id=$2"
    ))
    .bind(space)
    .bind(id)
    .fetch_one(conn)
    .await?)
}

pub(super) async fn by_slug(
    conn: &mut PgConnection,
    space: Uuid,
    slug: &str,
) -> Result<WikiPageDetail> {
    Ok(sqlx::query_as(concat!(
        page_select!(),
        " where p.space_id=$1 and p.slug=$2"
    ))
    .bind(space)
    .bind(slug)
    .fetch_one(conn)
    .await?)
}

fn check_base(current: &WikiPageDetail, expected: Option<Uuid>) -> Result<()> {
    if current.revision_id == expected {
        return Ok(());
    }
    Err(Error::Stale(Box::new(WikiConflict {
        detail: "The page changed. Review the current text before saving.",
        current_revision_id: current.revision_id,
        current_content_md: current.content_md.clone(),
        current_format: None,
        current_kind: current.page.kind.clone(),
    })))
}

/// The space row lock serializes structural writers. Recursive walks touch only
/// the proposed ancestry and moved subtree, not every page in the Wiki.
async fn placement(
    conn: &mut PgConnection,
    space: Uuid,
    id: Option<Uuid>,
    parent: Option<Uuid>,
) -> Result<()> {
    let ancestors: Vec<(Uuid, String)> = sqlx::query_as(
        "with recursive ancestors as (
            select page_id,parent_page_id,kind,1 as depth from wiki_page where space_id=$1 and page_id=$2
            union all select p.page_id,p.parent_page_id,p.kind,a.depth+1 from wiki_page p
                join ancestors a on a.parent_page_id=p.page_id where p.space_id=$1 and a.depth<5
         ) select page_id,kind from ancestors")
        .bind(space).bind(parent).fetch_all(&mut *conn).await?;
    if parent.is_some() && ancestors.is_empty() {
        return Err(AppError::NotFound.into());
    }
    if ancestors
        .iter()
        .any(|(ancestor, kind)| Some(*ancestor) == id || kind != "page")
    {
        return Err(invalid(
            "An entry cannot be placed under itself, the rules page or a file.",
        ));
    }
    let height: i32 = sqlx::query_scalar(
        "with recursive children as (
            select page_id,0 as depth from wiki_page where space_id=$1 and page_id=$2
            union all select p.page_id,c.depth+1 from wiki_page p join children c on p.parent_page_id=c.page_id
                where p.space_id=$1 and c.depth<4
         ) select coalesce(max(depth),0) from children")
        .bind(space).bind(id).fetch_one(&mut *conn).await?;
    if ancestors.len() + height as usize > 3 {
        return Err(invalid("The Wiki supports four levels of pages."));
    }
    Ok(())
}

fn cursor(value: Option<&str>) -> Result<Option<(DateTime<Utc>, Uuid)>> {
    value
        .map(|value| {
            let bytes = URL_SAFE_NO_PAD
                .decode(value)
                .map_err(|_| invalid("Invalid cursor."))?;
            serde_json::from_slice(&bytes).map_err(|_| invalid("Invalid cursor."))
        })
        .transpose()
}

/// Keeps one page of a `HISTORY_SIZE + 1` read and encodes where the next one starts.
fn next_cursor<T>(
    rows: &mut Vec<T>,
    key: impl Fn(&T) -> (DateTime<Utc>, Uuid),
) -> Result<Option<String>> {
    if rows.len() <= HISTORY_SIZE {
        return Ok(None);
    }
    rows.truncate(HISTORY_SIZE);
    let last = rows.last().map(key).ok_or(AppError::NotFound)?;
    Ok(Some(URL_SAFE_NO_PAD.encode(
        serde_json::to_vec(&last).map_err(|e| AppError::Internal(e.into()))?,
    )))
}

impl Access {
    pub async fn pages(&mut self) -> Result<WikiPageTree> {
        let pages = sqlx::query_as(
            "select p.*,c.mime,c.size,r.agent_name,r.agent_instance_id,r.author_user_id from wiki_page p left join wiki_revision r on r.revision_id=p.current_revision_id
             left join document d on d.id=r.document_id left join document_content c on c.id=d.current_content_id
             where p.space_id=$1 order by p.position,p.title,p.page_id",
        )
        .bind(self.space.id)
        .fetch_all(&mut *self.tx)
        .await?;
        Ok(WikiPageTree { pages })
    }

    pub async fn rules(&mut self) -> Result<WikiPageDetail> {
        let id: Option<Uuid> =
            sqlx::query_scalar("select page_id from wiki_page where space_id=$1 and kind='rules'")
                .bind(self.space.id)
                .fetch_optional(&mut *self.tx)
                .await?;
        match id {
            Some(id) => page(&mut self.tx, self.space.id, id).await,
            None => Ok(WikiPageDetail {
                page: WikiPageSummary {
                    slug: RULES.into(),
                    title: "Rules".into(),
                    kind: "rules".into(),
                    ..Default::default()
                },
                ..Default::default()
            }),
        }
    }

    /// A file entry is born with its accepted revision (`wiki_file_current`).
    async fn insert_page(
        &mut self,
        title: &str,
        parent: Option<Uuid>,
        position: i32,
        kind: &str,
        current: Option<Uuid>,
    ) -> Result<Uuid> {
        let id = Uuid::new_v4();
        let slug = if kind == "rules" {
            RULES.into()
        } else {
            id.simple().to_string()
        };
        sqlx::query("insert into wiki_page(page_id,space_id,slug,title,kind,parent_page_id,position,updated_by,current_revision_id)
            values($1,$2,$3,$4,$5,$6,$7,$8,$9)")
            .bind(id).bind(self.space.id).bind(slug).bind(title).bind(kind)
            .bind(parent).bind(position).bind(&self.person).bind(current).execute(&mut *self.tx).await?;
        Ok(id)
    }

    pub async fn create(&mut self, body: CreateWikiPageRequest) -> Result<WikiPageDetail> {
        content(&body.content_md, false)?;
        let title = title(&body.title)?;
        placement(&mut self.tx, self.space.id, None, body.parent_page_id).await?;
        let id = self
            .insert_page(&title, body.parent_page_id, body.position, "page", None)
            .await?;
        self.write(
            id,
            UpdateWikiContentRequest {
                content_md: body.content_md,
                base_revision_id: None,
            },
        )
        .await
    }

    pub async fn write_rules(&mut self, body: UpdateWikiContentRequest) -> Result<WikiPageDetail> {
        content(&body.content_md, true)?;
        let current = self.rules().await?;
        check_base(&current, body.base_revision_id)?;
        let id = if current.page.page_id.is_nil() {
            self.insert_page("Rules", None, 0, "rules", None).await?
        } else {
            current.page.page_id
        };
        self.write(id, body).await
    }

    pub async fn write(
        &mut self,
        id: Uuid,
        body: UpdateWikiContentRequest,
    ) -> Result<WikiPageDetail> {
        let current = page(&mut self.tx, self.space.id, id).await?;
        if current.page.kind == "file" {
            return Err(invalid(
                "A Wiki file changes only through an accepted version.",
            ));
        }
        content(&body.content_md, current.page.kind == "rules")?;
        check_base(&current, body.base_revision_id)?;
        let revision = Uuid::new_v4();
        sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,entry_kind,content_md,status,author_user_id)
            values($1,$2,$3,$4,$5,'published',$6)")
            .bind(revision).bind(self.space.id).bind(id).bind(&current.page.kind).bind(body.content_md)
            .bind(&self.person).execute(&mut *self.tx).await?;
        self.set_current(id, revision).await
    }

    async fn set_current(&mut self, id: Uuid, revision: Uuid) -> Result<WikiPageDetail> {
        sqlx::query(
            "update wiki_revision set status='superseded' where revision_id=
            (select current_revision_id from wiki_page where page_id=$1 and space_id=$2)",
        )
        .bind(id)
        .bind(self.space.id)
        .execute(&mut *self.tx)
        .await?;
        sqlx::query(
            "update wiki_page set current_revision_id=$3,updated_by=$4,
            updated_at=clock_timestamp() where page_id=$1 and space_id=$2",
        )
        .bind(id)
        .bind(self.space.id)
        .bind(revision)
        .bind(&self.person)
        .execute(&mut *self.tx)
        .await?;
        page(&mut self.tx, self.space.id, id).await
    }

    pub async fn metadata(
        &mut self,
        id: Uuid,
        body: UpdateWikiMetadataRequest,
    ) -> Result<WikiPageSummary> {
        let current = page(&mut self.tx, self.space.id, id).await?;
        if current.page.kind == "rules" {
            return Err(invalid("The rules page cannot be renamed or moved."));
        }
        if body.move_to_root && body.parent_page_id.is_some() {
            return Err(invalid("Choose one destination."));
        }
        let parent = if body.move_to_root {
            None
        } else {
            body.parent_page_id.or(current.page.parent_page_id)
        };
        placement(&mut self.tx, self.space.id, Some(id), parent).await?;
        let title = match body.title {
            Some(value) => title(&value)?,
            None => current.page.title.clone(),
        };
        if current.page.kind == "file" {
            same_extension(&title, &current.page.title)?;
        }
        sqlx::query(
            "update wiki_page set title=$3,parent_page_id=$4,position=$5,updated_by=$6,
            updated_at=clock_timestamp() where page_id=$1 and space_id=$2",
        )
        .bind(id)
        .bind(self.space.id)
        .bind(title)
        .bind(parent)
        .bind(body.position.unwrap_or(current.page.position))
        .bind(&self.person)
        .execute(&mut *self.tx)
        .await?;
        Ok(page(&mut self.tx, self.space.id, id).await?.page)
    }

    /// Deleting an entry also deletes its proposals and those creating entries under it (D21).
    pub async fn delete(&mut self, id: Uuid) -> Result<()> {
        let current = page(&mut self.tx, self.space.id, id).await?;
        if current.page.kind == "rules" {
            return Err(invalid("The rules page cannot be deleted."));
        }
        let children: bool =
            sqlx::query_scalar("select exists(select 1 from wiki_page where parent_page_id=$1)")
                .bind(id)
                .fetch_one(&mut *self.tx)
                .await?;
        if children {
            return Err(
                AppError::Conflict("Delete or move this page's children first.".into()).into(),
            );
        }
        sqlx::query("delete from wiki_page where page_id=$1 and space_id=$2")
            .bind(id)
            .bind(self.space.id)
            .execute(&mut *self.tx)
            .await?;
        Ok(())
    }

    pub async fn restore(
        &mut self,
        id: Uuid,
        revision: Uuid,
        validate: impl FnOnce(&ProposalRow) -> Result<()>,
    ) -> Result<WikiPageDetail> {
        let row: ProposalRow = sqlx::query_as(
            "select * from wiki_revision where space_id=$1 and page_id=$2
            and revision_id=$3 and status in ('published','superseded')",
        )
        .bind(self.space.id)
        .bind(id)
        .bind(revision)
        .fetch_one(&mut *self.tx)
        .await?;
        validate(&row)?;
        let base = page(&mut self.tx, self.space.id, id).await?.revision_id;
        self.write(
            id,
            UpdateWikiContentRequest {
                content_md: row.content_md,
                base_revision_id: base,
            },
        )
        .await
    }

    pub async fn history(
        &mut self,
        id: Uuid,
        cursor_value: Option<&str>,
    ) -> Result<WikiRevisionList> {
        // Ensure an empty history cannot disclose whether another space owns an id.
        page(&mut self.tx, self.space.id, id).await?;
        let before = cursor(cursor_value)?;
        #[derive(sqlx::FromRow)]
        struct Row {
            #[sqlx(flatten)]
            summary: WikiRevisionSummary,
            content_md: String,
        }
        let mut rows: Vec<Row> = sqlx::query_as("select r.* from wiki_revision r where r.space_id=$1 and r.page_id=$2
            and r.status in ('published','superseded') and ($3::timestamptz is null or (r.created_at,r.revision_id)<($3,$4))
            order by r.created_at desc,r.revision_id desc limit 51")
            .bind(self.space.id).bind(id).bind(before.map(|b| b.0)).bind(before.map(|b| b.1))
            .fetch_all(&mut *self.tx).await?;
        let next_cursor =
            next_cursor(&mut rows, |r| (r.summary.created_at, r.summary.revision_id))?;
        let mut result = WikiRevisionList {
            revisions: vec![],
            contents: Default::default(),
            next_cursor,
            authors: Default::default(),
        };
        for row in rows {
            result
                .contents
                .insert(row.summary.revision_id, row.content_md);
            result.revisions.push(row.summary);
        }
        Ok(result)
    }

    /// The parent of a new entry, with the tree limits checked and a free sibling name.
    pub(super) async fn new_entry(
        &mut self,
        parent_slug: Option<&str>,
        name: &str,
    ) -> Result<Option<Uuid>> {
        let parent = match parent_slug {
            Some(slug) => Some(
                by_slug(&mut self.tx, self.space.id, slug)
                    .await?
                    .page
                    .page_id,
            ),
            None => None,
        };
        placement(&mut self.tx, self.space.id, None, parent).await?;
        self.free_name(parent, name).await?;
        Ok(parent)
    }

    /// Named destination resolution is serialized with Wiki writers. A new page
    /// commits only with the first file; another file in the batch reuses it.
    pub(super) async fn file_destination(
        &mut self,
        parent_slug: Option<&str>,
        destination: &str,
        filename: &str,
        create: bool,
    ) -> Result<Option<Uuid>> {
        let name = title(destination)?;
        let parent = match parent_slug {
            Some(slug) => Some(
                by_slug(&mut self.tx, self.space.id, slug)
                    .await?
                    .page
                    .page_id,
            ),
            None => None,
        };
        placement(&mut self.tx, self.space.id, None, parent).await?;
        let found: Option<(Uuid, String)> = sqlx::query_as(
            "select page_id,kind from wiki_page where space_id=$1 and parent_page_id is not distinct from $2
             and wiki_title_key(title)=wiki_title_key($3)")
            .bind(self.space.id).bind(parent).bind(&name).fetch_optional(&mut *self.tx).await?;
        let id = if let Some((id, kind)) = found {
            if kind != "page" {
                return Err(invalid("The destination name belongs to a file."));
            }
            Some(id)
        } else if create {
            Some(
                self.create(CreateWikiPageRequest {
                    title: name,
                    content_md: String::new(),
                    parent_page_id: parent,
                    position: 0,
                })
                .await?
                .page
                .page_id,
            )
        } else {
            // A file must fit one level below the prospective page as well.
            let depth: i64 = sqlx::query_scalar("with recursive a as (
                select page_id,parent_page_id from wiki_page where page_id=$1 and space_id=$2
                union all select p.page_id,p.parent_page_id from wiki_page p join a on p.page_id=a.parent_page_id
                where p.space_id=$2) select count(*) from a")
                .bind(parent).bind(self.space.id).fetch_one(&mut *self.tx).await?;
            if depth >= 3 {
                return Err(invalid("The destination is too deep to contain files."));
            }
            None
        };
        if let Some(id) = id {
            placement(&mut self.tx, self.space.id, None, Some(id)).await?;
            self.free_name(Some(id), filename).await?;
        }
        Ok(id)
    }

    async fn free_name(&mut self, parent: Option<Uuid>, name: &str) -> Result<()> {
        let taken: bool = sqlx::query_scalar("select exists(select 1 from wiki_page where space_id=$1
            and parent_page_id is not distinct from $2 and wiki_title_key(title)=wiki_title_key($3))")
            .bind(self.space.id).bind(parent).bind(name).fetch_one(&mut *self.tx).await?;
        if taken {
            return Err(
                AppError::Conflict("A sibling entry already has this title.".into()).into(),
            );
        }
        Ok(())
    }

    pub async fn propose_page(&mut self, body: ProposeWikiPageRequest) -> Result<WikiProposal> {
        let name = title(&body.title)?;
        content(&body.content_md, false)?;
        let parent = self.new_entry(body.parent_slug.as_deref(), &name).await?;
        let id = Uuid::new_v4();
        self.insert_proposal(
            id,
            "page",
            None,
            None,
            Some(&name),
            parent,
            &body.content_md,
            None,
            None,
        )
        .await?;
        self.settle(id).await
    }

    pub async fn propose_edit(&mut self, body: ProposeWikiEditRequest) -> Result<WikiProposal> {
        let current = by_slug(&mut self.tx, self.space.id, &body.slug).await?;
        if current.page.kind == "rules" {
            return Err(AppError::Forbidden.into());
        }
        if current.page.kind == "file" {
            return Err(invalid("A Wiki file changes only through a file version."));
        }
        content(&body.content_md, false)?;
        check_base(&current, Some(body.base_revision_id))?;
        if current.content_md == body.content_md {
            return Err(AppError::Conflict(
                "This proposal would not change the page's text.".into(),
            )
            .into());
        }
        let id = Uuid::new_v4();
        let base = Some(body.base_revision_id);
        self.insert_proposal(
            id,
            "page",
            Some(current.page.page_id),
            base,
            None,
            None,
            &body.content_md,
            None,
            None,
        )
        .await?;
        self.settle(id).await
    }

    /// Provenance comes only from a checked conversation: SQL verifies the draft's
    /// author, agent and agent name against it. A file revision owns its Wiki copy.
    #[allow(clippy::too_many_arguments)]
    pub(super) async fn insert_proposal(
        &mut self,
        id: Uuid,
        kind: &str,
        page: Option<Uuid>,
        base: Option<Uuid>,
        title: Option<&str>,
        parent: Option<Uuid>,
        text: &str,
        source_writable_document_id: Option<&str>,
        source_workspace_path: Option<&str>,
    ) -> Result<()> {
        let (agent, name) = self.agent.clone().unzip();
        sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,entry_kind,document_id,base_revision_id,
            content_md,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title,proposed_parent_page_id,source_writable_document_id,source_workspace_path)
            values($1,$2,$3,$4,case when $4='file' then $1 end,$5,$6,'proposed',$7,$8,$9,$10,$11,$12,$13,$14)")
            .bind(id).bind(self.space.id).bind(page).bind(kind).bind(base).bind(text).bind(&self.person)
            .bind(agent).bind(name).bind(self.session).bind(title).bind(parent).bind(source_writable_document_id).bind(source_workspace_path)
            .execute(&mut *self.tx).await?;
        Ok(())
    }

    /// The person's own gesture confirms: an editor's acceptance is the same gesture
    /// (D7), a member's waits for an editor. A delegated turn only drafts (D5).
    pub(super) async fn settle(&mut self, id: Uuid) -> Result<WikiProposal> {
        if !self.delegated {
            if self.editor {
                self.accept(id).await?;
            } else {
                sqlx::query("update wiki_revision set session_id=null where revision_id=$1 and session_id is not null")
                    .bind(id).execute(&mut *self.tx).await?;
            }
        }
        self.view(id).await
    }

    /// Drafts are their author's, in their live conversation; pending proposals are
    /// their author's and the editors' (D9); accepted revisions are every reader's.
    pub(super) async fn visible(&mut self, id: Uuid) -> Result<ProposalRow> {
        let row: ProposalRow =
            sqlx::query_as("select * from wiki_revision where revision_id=$1 and space_id=$2")
                .bind(id)
                .bind(self.space.id)
                .fetch_one(&mut *self.tx)
                .await?;
        let author = row.author_user_id == self.person;
        match (row.status == "proposed", row.session_id) {
            (false, _) => {}
            (true, Some(session)) if author => {
                self.own_session(session).await?;
            }
            (true, None) if author || self.editor => {}
            _ => return Err(AppError::NotFound.into()),
        }
        Ok(row)
    }

    async fn view(&mut self, id: Uuid) -> Result<WikiProposal> {
        Ok(
            sqlx::query_as(concat!(proposal_select!(), " where r.revision_id=$1"))
                .bind(id)
                .fetch_one(&mut *self.tx)
                .await?,
        )
    }

    pub async fn proposal(&mut self, id: Uuid) -> Result<WikiProposal> {
        self.visible(id).await?;
        self.view(id).await
    }

    /// The pending queue: an editor's whole queue, otherwise the person's own (D9).
    pub async fn proposals(&mut self, cursor_value: Option<&str>) -> Result<WikiProposalList> {
        let before = cursor(cursor_value)?;
        let mut rows: Vec<WikiProposal> = sqlx::query_as(concat!(proposal_select!(),
            " where r.space_id=$1 and r.status='proposed' and r.session_id is null and ($2 or r.author_user_id=$3)
            and ($4::timestamptz is null or (r.created_at,r.revision_id)<($4,$5))
            order by r.created_at desc,r.revision_id desc limit 51"))
            .bind(self.space.id).bind(self.editor).bind(&self.person).bind(before.map(|b| b.0)).bind(before.map(|b| b.1))
            .fetch_all(&mut *self.tx).await?;
        let next_cursor = next_cursor(&mut rows, |r| (r.created_at, r.proposal_id))?;
        Ok(WikiProposalList {
            proposals: rows,
            next_cursor,
            authors: Default::default(),
        })
    }

    /// The author confirms their draft (`draft`) from the conversation they still own,
    /// or an editor accepts a pending proposal.
    pub async fn decide(
        &mut self,
        id: Uuid,
        draft: bool,
        validate: impl FnOnce(&ProposalRow) -> Result<()>,
    ) -> Result<WikiProposal> {
        let row = self.visible(id).await?;
        if row.status != "proposed" || row.session_id.is_some() != draft {
            return Err(AppError::NotFound.into());
        }
        validate(&row)?;
        self.settle(id).await
    }

    /// Withdrawal, refusal and decline delete the proposal: nothing keeps it (D8, D11).
    pub async fn delete_proposal(&mut self, id: Uuid) -> Result<()> {
        if self.visible(id).await?.status != "proposed" {
            return Err(AppError::NotFound.into());
        }
        sqlx::query("delete from wiki_revision where revision_id=$1")
            .bind(id)
            .execute(&mut *self.tx)
            .await?;
        Ok(())
    }

    /// The space row lock serializes arbitration: a second acceptance finds no
    /// proposal, never a second entry. An outdated proposal is refused (D17).
    async fn accept(&mut self, id: Uuid) -> Result<()> {
        let row: ProposalRow = sqlx::query_as(
            "select * from wiki_revision where revision_id=$1 and space_id=$2 and status='proposed'",
        )
        .bind(id)
        .bind(self.space.id)
        .fetch_one(&mut *self.tx)
        .await?;
        let file = row.entry_kind == "file";
        let page_id = match row.page_id {
            Some(page_id) => {
                check_base(
                    &page(&mut self.tx, self.space.id, page_id).await?,
                    row.base_revision_id,
                )?;
                page_id
            }
            None => {
                let title = row.proposed_title.as_deref().ok_or(AppError::NotFound)?;
                placement(
                    &mut self.tx,
                    self.space.id,
                    None,
                    row.proposed_parent_page_id,
                )
                .await?;
                self.free_name(row.proposed_parent_page_id, title).await?;
                let current = file.then_some(id);
                self.insert_page(
                    title,
                    row.proposed_parent_page_id,
                    0,
                    &row.entry_kind,
                    current,
                )
                .await?
            }
        };
        // Accepted content belongs to its entry, never to its proposed destination.
        sqlx::query(
            "update wiki_revision set status='published',page_id=$2,session_id=null,proposed_parent_page_id=null,
            reviewed_at=clock_timestamp(),reviewed_by=$3 where revision_id=$1",
        )
        .bind(id)
        .bind(page_id)
        .bind(&self.person)
        .execute(&mut *self.tx)
        .await?;
        if !file {
            self.set_current(page_id, id).await?;
        } else if let Some(previous) = row.page_id.and(row.base_revision_id) {
            // Files keep only their current version (D19); SQL retires the replaced copy.
            sqlx::query("update wiki_page set current_revision_id=$2,updated_by=$3,updated_at=clock_timestamp() where page_id=$1")
                .bind(page_id).bind(id).bind(&self.person).execute(&mut *self.tx).await?;
            sqlx::query("delete from wiki_revision where revision_id=$1")
                .bind(previous)
                .execute(&mut *self.tx)
                .await?;
        }
        Ok(())
    }

    /// The bytes of a file revision the reader may see, named after its entry.
    pub async fn revision_file(
        &mut self,
        id: Uuid,
        preview: bool,
    ) -> Result<(Uuid, String, String, i64, String)> {
        self.visible(id).await?;
        Ok(sqlx::query_as("select c.id,c.object_key,coalesce(p.title,r.proposed_title)||case when $3 then '.pdf' else '' end,
            c.size,c.sha256 from wiki_revision r join document d on d.id=r.document_id
            join document_content c on case when $3 then c.source_content_id=d.current_content_id else c.id=d.current_content_id end
            left join wiki_page p on p.page_id=r.page_id
            where r.revision_id=$1 and r.space_id=$2 and d.deletion_id is null and c.published_at is not null and c.cleaned_at is null")
            .bind(id).bind(self.space.id).bind(preview).fetch_one(&mut *self.tx).await?)
    }
}
