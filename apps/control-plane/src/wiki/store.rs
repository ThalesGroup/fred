// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{access::Access, *};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use chrono::{DateTime, Utc};
use sqlx::PgConnection;
use uuid::Uuid;

#[derive(sqlx::FromRow)]
struct PageRow {
    #[sqlx(flatten)]
    page: WikiPageSummary,
    content_md: String,
    revision_id: Option<Uuid>,
    author_kind: String,
}
impl From<PageRow> for WikiPageDetail {
    fn from(row: PageRow) -> Self {
        Self {
            page: row.page,
            content_md: row.content_md,
            revision_id: row.revision_id,
            author_kind: row.author_kind,
            author_name: None,
        }
    }
}

pub(super) async fn page(conn: &mut PgConnection, space: Uuid, id: Uuid) -> Result<WikiPageDetail> {
    let row: PageRow = sqlx::query_as(
        "select p.*,p.current_revision_id as revision_id,coalesce(r.content_md,'') as content_md,
         coalesce(r.author_kind,'human') as author_kind from wiki_page p
         left join wiki_revision r on r.revision_id=p.current_revision_id
         where p.space_id=$1 and p.page_id=$2",
    )
    .bind(space)
    .bind(id)
    .fetch_one(conn)
    .await?;
    Ok(row.into())
}

pub(super) async fn by_slug(
    conn: &mut PgConnection,
    space: Uuid,
    slug: &str,
) -> Result<WikiPageDetail> {
    let id = sqlx::query_scalar("select page_id from wiki_page where space_id=$1 and slug=$2")
        .bind(space)
        .bind(slug)
        .fetch_one(&mut *conn)
        .await?;
    page(conn, space, id).await
}

fn check_base(current: &WikiPageDetail, expected: Option<Uuid>) -> Result<()> {
    if current.revision_id == expected {
        return Ok(());
    }
    Err(Error::Stale(WikiConflict {
        detail: "The page changed. Review the current text before saving.",
        current_revision_id: current.revision_id,
        current_content_md: current.content_md.clone(),
    }))
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
        .any(|(ancestor, kind)| Some(*ancestor) == id || kind == "rules")
    {
        return Err(invalid(
            "A page cannot be moved under itself or the rules page.",
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

impl Access {
    pub async fn pages(&mut self) -> Result<WikiPageTree> {
        let pages = sqlx::query_as(
            "select * from wiki_page where space_id=$1 order by position,title,page_id",
        )
        .bind(self.space)
        .fetch_all(&mut *self.tx)
        .await?;
        Ok(WikiPageTree { pages })
    }

    pub async fn rules(&mut self) -> Result<WikiPageDetail> {
        let id: Option<Uuid> =
            sqlx::query_scalar("select page_id from wiki_page where space_id=$1 and kind='rules'")
                .bind(self.space)
                .fetch_optional(&mut *self.tx)
                .await?;
        match id {
            Some(id) => page(&mut self.tx, self.space, id).await,
            None => Ok(WikiPageDetail {
                page: WikiPageSummary {
                    page_id: Uuid::nil(),
                    slug: RULES.into(),
                    title: "Rules".into(),
                    kind: "rules".into(),
                    parent_page_id: None,
                    position: 0,
                    needs_review: false,
                    updated_at: None,
                    updated_by: String::new(),
                },
                content_md: String::new(),
                revision_id: None,
                author_kind: "human".into(),
                author_name: None,
            }),
        }
    }

    async fn insert_page(
        &mut self,
        title: &str,
        parent: Option<Uuid>,
        position: i32,
        rules: bool,
    ) -> Result<Uuid> {
        let id = Uuid::new_v4();
        let slug = if rules {
            RULES.into()
        } else {
            id.simple().to_string()
        };
        sqlx::query("insert into wiki_page(page_id,space_id,slug,title,kind,parent_page_id,position,updated_by)
            values($1,$2,$3,$4,$5,$6,$7,$8)")
            .bind(id).bind(self.space).bind(slug).bind(title).bind(if rules {"rules"} else {"page"})
            .bind(parent).bind(position).bind(&self.person).execute(&mut *self.tx).await?;
        Ok(id)
    }

    pub async fn create(&mut self, body: CreateWikiPageRequest) -> Result<WikiPageDetail> {
        content(&body.content_md, false)?;
        let title = title(&body.title)?;
        placement(&mut self.tx, self.space, None, body.parent_page_id).await?;
        let id = self
            .insert_page(&title, body.parent_page_id, body.position, false)
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
            self.insert_page("Rules", None, 0, true).await?
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
        let current = page(&mut self.tx, self.space, id).await?;
        content(&body.content_md, current.page.kind == "rules")?;
        check_base(&current, body.base_revision_id)?;
        let revision = Uuid::new_v4();
        sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,content_md,status,author_user_id,author_kind)
            values($1,$2,$3,$4,'published',$5,'human')")
            .bind(revision).bind(self.space).bind(id).bind(body.content_md).bind(&self.person)
            .execute(&mut *self.tx).await?;
        self.set_current(id, revision, false).await
    }

    async fn set_current(
        &mut self,
        id: Uuid,
        revision: Uuid,
        agent: bool,
    ) -> Result<WikiPageDetail> {
        sqlx::query(
            "update wiki_revision set status='superseded' where revision_id=
            (select current_revision_id from wiki_page where page_id=$1 and space_id=$2)",
        )
        .bind(id)
        .bind(self.space)
        .execute(&mut *self.tx)
        .await?;
        sqlx::query(
            "update wiki_page set current_revision_id=$3,needs_review=$4,updated_by=$5,
            updated_at=clock_timestamp() where page_id=$1 and space_id=$2",
        )
        .bind(id)
        .bind(self.space)
        .bind(revision)
        .bind(agent)
        .bind(&self.person)
        .execute(&mut *self.tx)
        .await?;
        page(&mut self.tx, self.space, id).await
    }

    pub async fn metadata(
        &mut self,
        id: Uuid,
        body: UpdateWikiMetadataRequest,
    ) -> Result<WikiPageSummary> {
        let current = page(&mut self.tx, self.space, id).await?;
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
        placement(&mut self.tx, self.space, Some(id), parent).await?;
        let title = match body.title {
            Some(value) => title(&value)?,
            None => current.page.title,
        };
        sqlx::query(
            "update wiki_page set title=$3,parent_page_id=$4,position=$5,updated_by=$6,
            updated_at=clock_timestamp() where page_id=$1 and space_id=$2",
        )
        .bind(id)
        .bind(self.space)
        .bind(title)
        .bind(parent)
        .bind(body.position.unwrap_or(current.page.position))
        .bind(&self.person)
        .execute(&mut *self.tx)
        .await?;
        Ok(page(&mut self.tx, self.space, id).await?.page)
    }

    pub async fn delete(&mut self, id: Uuid) -> Result<()> {
        let current = page(&mut self.tx, self.space, id).await?;
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
            .bind(self.space)
            .execute(&mut *self.tx)
            .await?;
        Ok(())
    }

    pub async fn review(&mut self, id: Uuid, body: WikiReviewRequest) -> Result<WikiPageSummary> {
        let current = page(&mut self.tx, self.space, id).await?;
        check_base(&current, Some(body.base_revision_id))?;
        sqlx::query("update wiki_page set needs_review=$3 where page_id=$1 and space_id=$2")
            .bind(id)
            .bind(self.space)
            .bind(body.needs_review)
            .execute(&mut *self.tx)
            .await?;
        if !body.needs_review && current.page.needs_review {
            sqlx::query("update wiki_revision set reviewed_at=clock_timestamp(),reviewed_by=$2 where revision_id=$1")
                .bind(body.base_revision_id).bind(&self.person).execute(&mut *self.tx).await?;
        }
        Ok(page(&mut self.tx, self.space, id).await?.page)
    }

    pub async fn restore(&mut self, id: Uuid, revision: Uuid) -> Result<WikiPageDetail> {
        let text = sqlx::query_scalar(
            "select content_md from wiki_revision where space_id=$1 and page_id=$2
            and revision_id=$3 and status in ('published','superseded')",
        )
        .bind(self.space)
        .bind(id)
        .bind(revision)
        .fetch_one(&mut *self.tx)
        .await?;
        let base = page(&mut self.tx, self.space, id).await?.revision_id;
        self.write(
            id,
            UpdateWikiContentRequest {
                content_md: text,
                base_revision_id: base,
            },
        )
        .await
    }

    pub async fn history(&mut self, id: Uuid, cursor: Option<&str>) -> Result<WikiRevisionList> {
        // Ensure an empty history cannot disclose whether another space owns an id.
        page(&mut self.tx, self.space, id).await?;
        let before: Option<(DateTime<Utc>, Uuid)> = cursor
            .map(|value| {
                let bytes = URL_SAFE_NO_PAD
                    .decode(value)
                    .map_err(|_| invalid("Invalid history cursor."))?;
                serde_json::from_slice(&bytes).map_err(|_| invalid("Invalid history cursor."))
            })
            .transpose()?;
        #[derive(sqlx::FromRow)]
        struct Row {
            #[sqlx(flatten)]
            summary: WikiRevisionSummary,
            content_md: String,
        }
        let mut rows: Vec<Row> = sqlx::query_as("select r.*,a.display_name as agent_name from wiki_revision r
            left join agent_instance a on a.agent_instance_id=r.agent_instance_id and a.space_id=r.space_id
            where r.space_id=$1 and r.page_id=$2
            and r.status in ('published','superseded') and ($3::timestamptz is null or (r.created_at,r.revision_id)<($3,$4))
            order by r.created_at desc,r.revision_id desc limit 51")
            .bind(self.space).bind(id).bind(before.map(|b| b.0)).bind(before.map(|b| b.1))
            .fetch_all(&mut *self.tx).await?;
        let next_cursor = if rows.len() > HISTORY_SIZE {
            let last = &rows[HISTORY_SIZE - 1].summary;
            Some(
                URL_SAFE_NO_PAD.encode(
                    serde_json::to_vec(&(last.created_at, last.revision_id))
                        .map_err(|e| AppError::Internal(e.into()))?,
                ),
            )
        } else {
            None
        };
        rows.truncate(HISTORY_SIZE);
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

    pub async fn propose_page(&mut self, body: ProposeWikiPageRequest) -> Result<WikiProposal> {
        let name = title(&body.title)?;
        let parent = match body.parent_slug {
            Some(slug) => Some(by_slug(&mut self.tx, self.space, &slug).await?.page.page_id),
            None => None,
        };
        placement(&mut self.tx, self.space, None, parent).await?;
        let duplicate: bool = sqlx::query_scalar("select exists(select 1 from wiki_page where space_id=$1
            and parent_page_id is not distinct from $2
            and lower(btrim(regexp_replace(title,'[[:space:]]+',' ','g')))=lower(btrim(regexp_replace($3,'[[:space:]]+',' ','g'))))")
            .bind(self.space).bind(parent).bind(&name).fetch_one(&mut *self.tx).await?;
        if duplicate {
            return Err(AppError::Conflict("A sibling page already has this title.".into()).into());
        }
        self.propose(None, None, Some(name), parent, body.content_md)
            .await
    }

    pub async fn propose_edit(&mut self, body: ProposeWikiEditRequest) -> Result<WikiProposal> {
        let current = by_slug(&mut self.tx, self.space, &body.slug).await?;
        if current.page.kind == "rules" {
            return Err(AppError::Forbidden.into());
        }
        check_base(&current, Some(body.base_revision_id))?;
        if current.content_md == body.content_md {
            return Err(AppError::Conflict(
                "This proposal would not change the page's text.".into(),
            )
            .into());
        }
        self.propose(
            Some(current.page.page_id),
            Some(body.base_revision_id),
            None,
            None,
            body.content_md,
        )
        .await
    }

    async fn propose(
        &mut self,
        page: Option<Uuid>,
        base: Option<Uuid>,
        title: Option<String>,
        parent: Option<Uuid>,
        text: String,
    ) -> Result<WikiProposal> {
        content(&text, false)?;
        // Only an admitted workload can attribute a proposal to an agent.
        let (session, agent) = self.session.zip(self.agent).ok_or(AppError::Forbidden)?;
        let id = Uuid::new_v4();
        let expires = self
            .proposal_retention
            .after(Utc::now())
            .map_err(AppError::from)?;
        sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,base_revision_id,content_md,status,
            author_user_id,author_kind,agent_instance_id,session_id,proposed_title,proposed_parent_page_id,expires_at)
            values($1,$2,$3,$4,$5,'proposed',$6,'agent',$7,$8,$9,$10,$11)")
            .bind(id).bind(self.space).bind(page).bind(base).bind(text).bind(&self.person)
            .bind(agent).bind(session).bind(title).bind(parent).bind(expires).execute(&mut *self.tx).await?;
        self.proposal(id).await
    }

    async fn pending(&mut self, id: Uuid) -> Result<ProposalRow> {
        let row: ProposalRow = sqlx::query_as("select * from wiki_revision where revision_id=$1 and space_id=$2
            and author_user_id=$3 and status='proposed' and expires_at>clock_timestamp() for update")
            .bind(id).bind(self.space).bind(&self.person).fetch_one(&mut *self.tx).await?;
        self.own_session(row.session_id).await?;
        Ok(row)
    }

    pub async fn proposal(&mut self, id: Uuid) -> Result<WikiProposal> {
        let row = self.pending(id).await?;
        let current = match row.page_id {
            Some(id) => Some(page(&mut self.tx, self.space, id).await?),
            None => None,
        };
        let parent_slug = match row.proposed_parent_page_id {
            Some(id) => Some(page(&mut self.tx, self.space, id).await?.page.slug),
            None => None,
        };
        Ok(WikiProposal {
            proposal_id: id,
            kind: if current.is_some() { "edit" } else { "page" }.into(),
            title: current
                .as_ref()
                .map(|p| p.page.title.clone())
                .or(row.proposed_title)
                .unwrap_or_default(),
            slug: current.as_ref().map(|p| p.page.slug.clone()),
            parent_slug,
            content_md: row.content_md,
            current_content_md: current.map(|p| p.content_md).unwrap_or_default(),
            created_at: row.created_at,
            author_user_id: self.person.clone(),
            agent_instance_id: row.agent_instance_id,
        })
    }

    pub async fn publish(&mut self, id: Uuid) -> Result<WikiPageDetail> {
        let row = self.pending(id).await?;
        let page_id = match row.page_id {
            Some(id) => {
                let current = page(&mut self.tx, self.space, id).await?;
                if current.page.kind == "rules" {
                    return Err(AppError::Forbidden.into());
                }
                check_base(&current, row.base_revision_id)?;
                id
            }
            None => {
                placement(&mut self.tx, self.space, None, row.proposed_parent_page_id).await?;
                self.insert_page(
                    row.proposed_title.as_deref().ok_or(AppError::NotFound)?,
                    row.proposed_parent_page_id,
                    0,
                    false,
                )
                .await?
            }
        };
        // The locked pending row also serializes with expiry. A second approval
        // sees no pending proposal, never a second page or revision.
        sqlx::query("update wiki_revision set status='published',page_id=$2 where revision_id=$1")
            .bind(id)
            .bind(page_id)
            .execute(&mut *self.tx)
            .await?;
        self.set_current(page_id, id, true).await
    }
}

#[derive(sqlx::FromRow)]
struct ProposalRow {
    page_id: Option<Uuid>,
    base_revision_id: Option<Uuid>,
    session_id: Uuid,
    content_md: String,
    proposed_title: Option<String>,
    proposed_parent_page_id: Option<Uuid>,
    created_at: DateTime<Utc>,
    agent_instance_id: Option<Uuid>,
}
