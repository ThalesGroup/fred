// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One UTC calendar for SQL, historical reads and frequency denominators.
//! French national holidays: https://www.service-public.gouv.fr/particuliers/vosdroits/F2405
use super::models::{AnalyticsCalendar, AnalyticsPeriod};
use chrono::{Datelike, Duration, NaiveDate};

fn holiday(day: NaiveDate) -> bool {
    if matches!(
        (day.month(), day.day()),
        (1, 1) | (5, 1) | (5, 8) | (7, 14) | (8, 15) | (11, 1) | (11, 11) | (12, 25)
    ) {
        return true;
    }
    // Gregorian computus; the public planner restricts years to 1970..9999.
    let y = day.year();
    let a = y % 19;
    let b = y / 100;
    let c = y % 100;
    let h = (19 * a + b - b / 4 - (b - (b + 8) / 25 + 1) / 3 + 15) % 30;
    let l = (32 + 2 * (b % 4) + 2 * (c / 4) - h - c % 4) % 7;
    let m = (a + 11 * h + 22 * l) / 451;
    let n = h + l - 7 * m + 114;
    NaiveDate::from_ymd_opt(y, (n / 31) as u32, (n % 31 + 1) as u32).is_some_and(|easter| {
        [1, 39, 50]
            .iter()
            .any(|&d| easter + Duration::days(d) == day)
    })
}
impl AnalyticsCalendar {
    pub(crate) fn counts(self, day: NaiveDate) -> bool {
        !(self.exclude_weekends && day.weekday().num_days_from_monday() >= 5
            || self.exclude_holidays && holiday(day))
    }
}
impl AnalyticsPeriod {
    pub(crate) fn dates(&self) -> impl Iterator<Item = NaiveDate> {
        let first = self.since.date_naive();
        let last = (self.until - Duration::nanoseconds(1)).date_naive();
        (0..=(last - first).num_days()).map(move |n| first + Duration::days(n))
    }
    pub(crate) fn excluded_dates(&self) -> Vec<NaiveDate> {
        self.dates().filter(|&d| !self.calendar.counts(d)).collect()
    }
    pub(crate) fn counted_days(&self) -> usize {
        self.dates().filter(|&d| self.calendar.counts(d)).count()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn national_calendar_and_half_open_utc_days() {
        let p: AnalyticsPeriod = serde_json::from_value(serde_json::json!({
            "since":"2026-01-01T00:00:00Z","until":"2026-01-05T00:00:00Z","timezone":"UTC",
            "calendar":{"exclude_weekends":true,"exclude_holidays":true}
        }))
        .unwrap();
        assert_eq!(p.counted_days(), 1);
        for d in ["2026-04-06", "2026-05-14", "2026-05-25"] {
            assert!(holiday(d.parse().unwrap()));
        }
        assert!(!holiday("2026-12-26".parse().unwrap()));
        assert!(!holiday("2026-04-03".parse().unwrap()));
    }
}
