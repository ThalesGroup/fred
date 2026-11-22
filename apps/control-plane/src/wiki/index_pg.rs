// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The sole SQL owner of the rebuildable Wiki search projection.
use super::*;
use fred_wiki::{Page, index_document};
use futures::future::BoxFuture;
use sqlx::PgConnection;

const INDEX_VERSION: i32 = 1;
pub(super) struct PostgresIndex;

// Identity comparisons only: the catalogue reloads the selected current revision
// under the space writer lock before supplying its text to project().
const STALE: &str = "p.kind='page' and p.current_revision_id is not null and
    (i.page_id is null or i.revision_id<>p.current_revision_id or i.title<>p.title or i.index_version<$1)";

impl WikiIndex for PostgresIndex {
    fn project<'a>(
        &'a self,
        conn: &'a mut PgConnection,
        space: Uuid,
        page: &'a WikiPageDetail,
    ) -> BoxFuture<'a, Result<()>> {
        Box::pin(async move {
            let Some(revision) = page.revision_id.filter(|_| page.page.kind == "page") else {
                return Ok(());
            };
            let parsed = Page::parse(&page.content_md).and_then(|page| {
                page.validate_native()?;
                Ok(page)
            });
            let document = parsed.as_ref().ok().map(index_document);
            // Nonconforming stored text is readable, and remains findable as raw untyped text.
            let page_type = document
                .as_ref()
                .map_or("untyped", |d| d.page_type.as_ref());
            let description = document.as_ref().and_then(|d| d.description.as_deref());
            let read_when = document.as_ref().and_then(|d| d.read_when.as_deref());
            let tags: Vec<&str> = document
                .as_ref()
                .map(|d| d.tags.iter().map(|s| s.as_ref()).collect())
                .unwrap_or_default();
            let aliases: Vec<&str> = document
                .as_ref()
                .map(|d| d.aliases.iter().map(|s| s.as_ref()).collect())
                .unwrap_or_default();
            let body = document
                .as_ref()
                .map_or(page.content_md.as_str(), |d| d.body);
            sqlx::query("insert into wiki_page_index(page_id,space_id,revision_id,title,index_version,
                page_type,description,read_when,aliases,tags,body,search_vector)
                values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                    setweight(to_tsvector('french',$4||' '||array_to_string($9::text[],' ')) ||
                              to_tsvector('english',$4||' '||array_to_string($9::text[],' ')), 'A') ||
                    setweight(to_tsvector('french',coalesce($7,'')||' '||coalesce($8,'')||' '||array_to_string($10::text[],' ')) ||
                              to_tsvector('english',coalesce($7,'')||' '||coalesce($8,'')||' '||array_to_string($10::text[],' ')), 'B') ||
                    setweight(to_tsvector('french',$11) || to_tsvector('english',$11), 'C'))
                on conflict(page_id) do update set space_id=excluded.space_id, revision_id=excluded.revision_id,
                    title=excluded.title,index_version=excluded.index_version,page_type=excluded.page_type,
                    description=excluded.description,read_when=excluded.read_when,aliases=excluded.aliases,
                    tags=excluded.tags,body=excluded.body,search_vector=excluded.search_vector
                where wiki_page_index.index_version<=excluded.index_version")
                .bind(page.page.page_id).bind(space).bind(revision).bind(&page.page.title).bind(INDEX_VERSION)
                .bind(page_type).bind(description).bind(read_when).bind(aliases).bind(tags).bind(body)
                .execute(conn).await?;
            Ok(())
        })
    }

    fn reconcile<'a>(&'a self, conn: &'a mut PgConnection) -> BoxFuture<'a, Result<bool>> {
        Box::pin(async move {
            let future: bool = sqlx::query_scalar(
                "select exists(select 1 from wiki_page_index where index_version>$1)",
            )
            .bind(INDEX_VERSION)
            .fetch_one(&mut *conn)
            .await?;
            if future {
                return Err(AppError::Internal(anyhow::anyhow!(
                    "Wiki index version is newer than this binary"
                ))
                .into());
            }
            let sql = format!("select s.id from space s where s.deletion_id is null and exists(
                select 1 from wiki_page p left join wiki_page_index i on i.page_id=p.page_id
                where p.space_id=s.id and {STALE}) order by s.id for no key update of s skip locked limit 1");
            let space: Option<Uuid> = sqlx::query_scalar(sqlx::AssertSqlSafe(sql))
                .bind(INDEX_VERSION)
                .fetch_optional(&mut *conn)
                .await?;
            if let Some(space) = space {
                let sql = format!("select p.page_id from wiki_page p left join wiki_page_index i on i.page_id=p.page_id
                    where p.space_id=$2 and {STALE} order by p.page_id limit 100");
                let pages: Vec<Uuid> = sqlx::query_scalar(sqlx::AssertSqlSafe(sql))
                    .bind(INDEX_VERSION)
                    .bind(space)
                    .fetch_all(&mut *conn)
                    .await?;
                for current in store::current_pages(conn, space, &pages).await? {
                    self.project(conn, space, &current).await?;
                }
                return Ok(true);
            }
            // A skipped writer/reconciler is pending work, not successful exhaustion.
            let sql = format!("select exists(select 1 from wiki_page p join space s on s.id=p.space_id
                left join wiki_page_index i on i.page_id=p.page_id where s.deletion_id is null and {STALE})");
            Ok(sqlx::query_scalar(sqlx::AssertSqlSafe(sql))
                .bind(INDEX_VERSION)
                .fetch_one(conn)
                .await?)
        })
    }

    fn search<'a>(
        &'a self,
        conn: &'a mut PgConnection,
        space: Uuid,
        query: &'a SearchQuery,
    ) -> BoxFuture<'a, Result<Vec<SearchCandidate>>> {
        Box::pin(async move {
            // Only 201 ranked identities are retained. The last detects truncation;
            // count/offset precede headline, so at most 3*limit excerpts are computed.
            Ok(sqlx::query_as("with languages as (select websearch_to_tsquery('french',$2) as fr, websearch_to_tsquery('english',$2) as en),
                q as (select fr,en,fr||en as terms from languages),
                ranked as materialized (
                    select i.page_id,ts_rank_cd(i.search_vector,q.terms) as rank from wiki_page_index i cross join q
                    where i.space_id=$1 and i.search_vector@@q.terms
                      and ($3::text is null or i.page_type=$3) and ($4::text is null or i.tags@>array[$4])
                    order by rank desc,i.page_id limit 201),
                candidates as (select page_id,rank,count(*) over() as candidate_count from ranked
                    order by rank desc,page_id limit $5 offset $6)
                select i.page_id,i.revision_id,i.page_type,i.description,c.candidate_count,
                    left(ts_headline(case when to_tsvector('french',i.body)@@q.fr then 'french'::regconfig
                        else 'english'::regconfig end,i.body,q.terms,
                    'StartSel=\"\", StopSel=\"\", MaxWords=20, MinWords=5, MaxFragments=1'),300) as excerpt
                from candidates c join wiki_page_index i on i.page_id=c.page_id cross join q
                order by c.rank desc,c.page_id")
                .bind(space).bind(&query.q).bind(&query.page_type).bind(&query.tag)
                .bind((3*query.limit) as i64).bind(query.offset as i64).fetch_all(conn).await?)
        })
    }
}

#[cfg(test)]
#[path = "../../tests/support/database.rs"]
mod test_database;

#[cfg(test)]
mod tests {
    use super::*;

    /// SQL only: no HTTP/auth, model calls or production capacity claim.
    #[tokio::test]
    #[ignore = "needs disposable Postgres; latency indicator, not a CI gate"]
    async fn wiki_search_latency_500_pages_in_five_spaces() {
        let pool = test_database::database().await;
        let org = Uuid::new_v4();
        sqlx::query(
            "insert into space(id,kind,name,organization_id) values($1,'organization',$1::text,$1)",
        )
        .bind(org)
        .execute(&pool)
        .await
        .unwrap();
        let mut spaces = Vec::new();
        let text = format!(
            "---\ntype: procedure\ndescription: Restarting production services\ntags: [operations, service]\nx-fred-aliases: [reboot]\n---\n{}",
            "Restarting services requires observing metrics. Redémarrage après maintenance. "
                .repeat(30)
        );
        for _ in 0..5 {
            let space = Uuid::new_v4();
            spaces.push(space);
            sqlx::query("insert into space(id,kind,name,organization_id,parent_id) values($1,'team',$1::text,$2,$2)")
                .bind(space).bind(org).execute(&pool).await.unwrap();
            let ids: Vec<Uuid> = (0..500).map(|_| Uuid::new_v4()).collect();
            let mut tx = pool.begin().await.unwrap();
            sqlx::query(
                "insert into wiki_page(page_id,space_id,slug,title,updated_by)
                select id,$1,id::text,'Service '||id::text,'fixture' from unnest($2::uuid[]) id",
            )
            .bind(space)
            .bind(&ids)
            .execute(&mut *tx)
            .await
            .unwrap();
            sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,entry_kind,content_md,status,author_user_id)
                select id,$1,id,'page',$3,'published','fixture' from unnest($2::uuid[]) id")
                .bind(space).bind(&ids).bind(&text).execute(&mut *tx).await.unwrap();
            sqlx::query("update wiki_page set current_revision_id=page_id where page_id=any($1)")
                .bind(&ids)
                .execute(&mut *tx)
                .await
                .unwrap();
            tx.commit().await.unwrap();
        }
        super::super::reconcile(&pool).await.unwrap();
        sqlx::query("analyze wiki_page_index")
            .execute(&pool)
            .await
            .unwrap();
        let mut times = Vec::new();
        let query = SearchQuery {
            q: "restart".into(),
            page_type: None,
            tag: None,
            limit: 10,
            offset: 0,
        };
        let mut conn = pool.acquire().await.unwrap();
        for round in 0..110 {
            let start = std::time::Instant::now();
            let result = PostgresIndex
                .search(&mut conn, spaces[round % 5], &query)
                .await
                .unwrap();
            assert_eq!(result.len(), 30);
            if round >= 10 {
                times.push(start.elapsed().as_secs_f64() * 1000.0);
            }
        }
        times.sort_by(f64::total_cmp);
        eprintln!(
            "Wiki search SQL: 5 spaces x 500 pages, {} chars/page, FR+EN repetitive service prose, limit10, 30 excerpts, 10 warmups/100 samples; p50={:.2}ms p99={:.2}ms; target50ms indicator only",
            text.chars().count(),
            times[49],
            times[98]
        );
    }
}
