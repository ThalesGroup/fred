// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use chrono::{DateTime, FixedOffset, NaiveDate};

use crate::{NodeRef, present};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrustTier {
    Unverified,
    MachineConfirmed,
    HumanReviewed,
}

/// Catalogue-supplied generation. `None` for the whole value means absent.
#[derive(Debug, Clone, Copy)]
pub struct Generation<'a> {
    pub at: Option<&'a str>,
}

#[derive(Debug, Clone, Copy)]
pub struct Verification<'a> {
    pub by: &'a str,
    pub at: &'a str,
}

/// Advisory only: never reads provenance from an imported/authored header.
/// The caller supplies actual confirmations for the relevant content revision.
/// Fred conservatively returns Unverified when generation exists but has no
/// usable date; OKF does not define currentness for that case.
pub fn trust_tier(generated: Option<Generation<'_>>, verified: &[Verification<'_>]) -> TrustTier {
    let generated_at = match generated {
        None => None,
        Some(generation) => match generation.at.and_then(timestamp) {
            Some(at) => Some(at),
            None => return TrustTier::Unverified,
        },
    };
    let mut tier = TrustTier::Unverified;
    for event in verified {
        let Some(at) = timestamp(event.at) else {
            continue;
        };
        if event.by.is_empty() || generated_at.is_some_and(|generated| at < generated) {
            continue;
        }
        if event
            .by
            .strip_prefix("human:")
            .is_some_and(|id| !id.is_empty())
        {
            return TrustTier::HumanReviewed;
        }
        tier = TrustTier::MachineConfirmed;
    }
    tier
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Freshness {
    Unspecified,
    Fresh,
    Stale,
    Malformed,
}

/// A date-only deadline starts at midnight UTC. Due means now >= deadline.
pub fn freshness(stale_after: Option<NodeRef<'_>>, now: DateTime<FixedOffset>) -> Freshness {
    let Some(value) = present(stale_after) else {
        return Freshness::Unspecified;
    };
    match value.as_str().as_deref().and_then(timestamp) {
        Some(deadline)
            if now < deadline.at || (now == deadline.at && !deadline.tail.is_empty()) =>
        {
            Freshness::Fresh
        }
        Some(_) => Freshness::Stale,
        None => Freshness::Malformed,
    }
}

// Chrono validates RFC 3339 but truncates fractions after nanoseconds. Keep the
// remaining digits for exact ordering; trimming zeros also makes .1 == .10.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Timestamp<'a> {
    at: DateTime<FixedOffset>,
    tail: &'a str,
}

pub(crate) fn timestamp(value: &str) -> Option<Timestamp<'_>> {
    if value.len() == 10
        && value.bytes().enumerate().all(|(index, byte)| {
            if index == 4 || index == 7 {
                byte == b'-'
            } else {
                byte.is_ascii_digit()
            }
        })
    {
        return NaiveDate::parse_from_str(value, "%Y-%m-%d")
            .ok()?
            .and_hms_opt(0, 0, 0)
            .map(|date| Timestamp {
                at: date.and_utc().fixed_offset(),
                tail: "",
            });
    }
    // Chrono also accepts a space separator; OKF specifies RFC 3339 date-time.
    if !matches!(value.as_bytes().get(10), Some(b'T' | b't')) {
        return None;
    }
    let at = DateTime::parse_from_rfc3339(value).ok()?;
    // This slices only a fraction already accepted by Chrono, not timestamp syntax.
    let tail = value
        .get(19..)
        .and_then(|suffix| suffix.strip_prefix('.'))
        .map(|fraction| {
            fraction
                .split(|c: char| !c.is_ascii_digit())
                .next()
                .unwrap_or_default()
        })
        .and_then(|fraction| fraction.get(9..))
        .unwrap_or_default()
        .trim_end_matches('0');
    Some(Timestamp { at, tail })
}
