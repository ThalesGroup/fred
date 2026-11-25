// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Catalogue states and retained receipts, in the existing authorized SQL snapshot.
use super::{
    models::*,
    statistics::{median, ratio},
};
use crate::{
    error::AppResult,
    sessions::usage::read::{UsageScope, collective_spaces, organization_spaces},
};
use sqlx::PgConnection;
use std::collections::BTreeMap;

pub(super) async fn read(
    conn: &mut PgConnection,
    scope: &UsageScope<'_>,
    q: &AnalyticsQuery,
    creator_statistics: bool,
) -> AppResult<BTreeMap<ConsumptionMeasure, String>> {
    use ConsumptionMeasure::*;
    let excluded = q.time.excluded_dates();
    if q.measures[0].reader() == ReaderKind::Inventory {
        let UsageScope::Space { id, team } = scope else {
            return Err(super::invalid("Inventory requires a collective space"));
        };
        let (available, created, documents): (String, String, String) = sqlx::query_as(concat!(
            "with scoped as (", collective_spaces!("$1", "$2"), "), agents as (",
            "select a.* from agent_instance a join space s on s.id=a.space_id ",
            "where a.space_id in (select * from scoped) and s.deletion_id is null) ",
            "select (select count(*)::text from agents where enabled), ",
            "(select count(*)::text from agents where created_at >= $3 and created_at < $4 ",
            "and (created_at at time zone 'UTC')::date <> all($5::date[])), ",
            "(select count(*)::text from document_upload where space_id in (select * from scoped) ",
            "and session_id is null and purpose='source' and status='stored' and completed_at >= $3 and completed_at < $4 ",
            "and (completed_at at time zone 'UTC')::date <> all($5::date[]))"
        ))
        .bind(id)
        .bind(team)
        .bind(q.time.since)
        .bind(q.time.until)
        .bind(&excluded)
        .fetch_one(conn)
        .await?;
        // No publication state exists for Weaver agents. Absence is not zero.
        return Ok(BTreeMap::from([
            (AgentsAvailable, available),
            (AgentsCreated, created),
            (DocumentsAdded, documents),
        ]));
    }
    // Group before returning: never expose creator identities, and refuse cardinality overflow.
    macro_rules! suffix {
        () => { concat!(
            " and s.deletion_id is null and p.deletion_id is null and s.created_at >= $3 and s.created_at < $4 ",
            "and (s.created_at at time zone 'UTC')::date <> all($5::date[]) ",
            "group by case when $6 then s.user_id else '' end limit 10001"
        ) };
    }
    let rows: Vec<i64> = match scope {
        UsageScope::Space { id, team } => {
            let sql = concat!(
                "select count(*) from session_metadata s join space p on p.id=s.space_id where s.space_id in (",
                collective_spaces!("$1", "$2"),
                ")",
                suffix!()
            );
            sqlx::query_scalar(sql)
                .bind(id)
                .bind(team)
                .bind(q.time.since)
                .bind(q.time.until)
                .bind(&excluded)
                .bind(creator_statistics)
                .fetch_all(conn)
                .await?
        }
        UsageScope::Person {
            subject,
            organization,
        } => {
            let sql = concat!(
                "select count(*) from session_metadata s join space p on p.id=s.space_id where s.user_id=$1 and s.space_id in (",
                organization_spaces!("$2"),
                ")",
                suffix!()
            );
            sqlx::query_scalar(sql)
                .bind(subject)
                .bind(organization)
                .bind(q.time.since)
                .bind(q.time.until)
                .bind(&excluded)
                .bind(creator_statistics)
                .fetch_all(conn)
                .await?
        }
    };
    if rows.len() > 10000 {
        return Err(super::too_large());
    }
    let mut counts: Vec<u128> = rows.into_iter().map(|n| n as u128).collect();
    counts.sort_unstable_by(|a, b| b.cmp(a));
    let total: u128 = counts.iter().sum();
    let mut values = BTreeMap::from([(RetainedConversations, total.to_string())]);
    if let Some(m) = median(counts.clone()) {
        values.insert(ConversationMedian, m);
    }
    if let Some(share) = ratio(counts.iter().take(counts.len().div_ceil(10)).sum(), total) {
        values.insert(ConversationConcentration, share);
    }
    for (measure, lo, hi) in [
        (CreatorsOne, 1, 1),
        (CreatorsTwoThree, 2, 3),
        (CreatorsFourTen, 4, 10),
        (CreatorsElevenThirty, 11, 30),
        (CreatorsThirtyPlus, 31, u128::MAX),
    ] {
        values.insert(
            measure,
            counts
                .iter()
                .filter(|&&n| n >= lo && n <= hi)
                .count()
                .to_string(),
        );
    }
    Ok(values)
}
