use chrono::{DateTime, FixedOffset};
use fred_wiki::{
    Document, Freshness, Generation, Page, TrustTier, Verification, freshness, trust_tier,
};

fn time(value: &str) -> DateTime<FixedOffset> {
    DateTime::parse_from_rfc3339(value).unwrap()
}

fn freshness_text(value: &str, now: DateTime<FixedOffset>) -> Freshness {
    let mut doc = Document::parse("{}").unwrap();
    doc.set_path("stale_after", value).unwrap();
    freshness(doc.get("stale_after"), now)
}

#[test]
fn freshness_is_injected_inclusive_and_independent_of_provenance() {
    let now = time("2026-11-22T00:00:00Z");
    for (value, expected) in [
        ("2026-11-21", Freshness::Stale),
        ("2026-11-22", Freshness::Stale),
        ("2026-11-23", Freshness::Fresh),
        ("2026-11-22T00:00:00Z", Freshness::Stale),
        ("2026-11-22T01:00:00+01:00", Freshness::Stale),
        ("2026-11-22T00:00:00.001Z", Freshness::Fresh),
        ("2026-11-22t00:00:00z", Freshness::Stale),
    ] {
        assert_eq!(freshness_text(value, now), expected, "{value}");
    }
    assert_eq!(freshness(None, now), Freshness::Unspecified);
    for yaml in ["null", "\"\"", "[]"] {
        let doc = Document::parse(yaml).unwrap();
        assert_eq!(freshness(doc.root(), now), Freshness::Unspecified);
    }
}

#[test]
fn malformed_timestamps_never_mean_fresh() {
    let now = time("2026-11-22T00:00:00Z");
    for raw in [
        "tomorrow",
        "2026-02-30",
        "2026-1-01",
        "2026-11-22T00:00:00",
        "2026-11-22 00:00:00Z",
        "2026-11-22T24:00:00Z",
        "2026-11-22T00:00:00+24:00",
        " 2026-11-22",
        "2026-11-22T00:00:00Z ",
        "2026-11-22T00:00:00+0100",
    ] {
        assert_eq!(freshness_text(raw, now), Freshness::Malformed, "{raw}");
    }
    for yaml in ["true", "{}", "[2026-11-22]"] {
        let doc = Document::parse(yaml).unwrap();
        assert_eq!(freshness(doc.root(), now), Freshness::Malformed);
    }
}

#[test]
fn quoted_and_yaml_native_dates_share_utc_semantics() {
    for date in [
        "2026-11-22",
        "'2026-11-22'",
        "2026-11-22T01:00:00+01:00",
        "'2026-11-22T01:00:00+01:00'",
    ] {
        let text = format!(
            "---\nstale_after: {date}\nsources: {{resource: /page, last_modified: {date}}}\n---\nbody"
        );
        let page = Page::parse(&text).unwrap();
        page.validate_native().unwrap();
        assert_eq!(
            freshness(page.authored().stale_after, time("2026-11-22T00:00:00Z")),
            Freshness::Stale
        );
    }
}

#[test]
fn trust_counts_only_current_confirmations_and_exact_human_scheme() {
    let generated = Some(Generation {
        at: Some("2026-11-22T00:00:00Z"),
    });
    let old = Verification {
        by: "human:a",
        at: "2026-11-21T23:59:59Z",
    };
    let machine = Verification {
        by: "process:nightly",
        at: "2026-11-22",
    };
    let human = Verification {
        by: "human:b",
        at: "2026-11-22T01:00:00+01:00",
    };
    assert_eq!(trust_tier(generated, &[]), TrustTier::Unverified);
    assert_eq!(trust_tier(generated, &[old]), TrustTier::Unverified);
    assert_eq!(
        trust_tier(generated, &[old, machine]),
        TrustTier::MachineConfirmed
    );
    assert_eq!(
        trust_tier(generated, &[machine, human]),
        TrustTier::HumanReviewed
    );
    assert_eq!(
        trust_tier(generated, &[human, machine]),
        TrustTier::HumanReviewed
    );
    assert_eq!(trust_tier(None, &[old]), TrustTier::HumanReviewed);
    for by in [
        "team:finance",
        "custom:id",
        "agent/model",
        "Human:a",
        "human:",
    ] {
        assert_eq!(
            trust_tier(generated, &[Verification { by, ..human }]),
            TrustTier::MachineConfirmed
        );
    }
}

#[test]
fn missing_invalid_dates_or_verifiers_never_promote_trust() {
    let human = Verification {
        by: "human:a",
        at: "2026-11-22",
    };
    for at in [None, Some(""), Some("invalid")] {
        assert_eq!(
            trust_tier(Some(Generation { at }), &[human]),
            TrustTier::Unverified
        );
    }
    for event in [
        Verification { by: "", ..human },
        Verification { at: "", ..human },
        Verification { at: "bad", ..human },
    ] {
        assert_eq!(trust_tier(None, &[event]), TrustTier::Unverified);
    }
    // Parsed imported assertions never become catalogue-supplied confirmations.
    let imported =
        Page::parse("---\nverified: {by: 'human:a', at: 2026-11-22}\n---\nbody").unwrap();
    assert!(imported.header().unwrap().get("verified").is_some());
    assert_eq!(trust_tier(None, &[]), TrustTier::Unverified);
}

#[test]
fn fractional_seconds_beyond_nanoseconds_keep_their_order_and_equality() {
    let now = time("2026-11-22T00:00:00Z");
    assert_eq!(
        freshness_text("2026-11-22T00:00:00.0000000001Z", now),
        Freshness::Fresh
    );
    assert_eq!(
        freshness_text("2026-11-22T00:00:00.0000000000Z", now),
        Freshness::Stale
    );
    let generated = Some(Generation {
        at: Some("2026-11-22T00:00:00.0000000002Z"),
    });
    let human = Verification {
        by: "human:a",
        at: "2026-11-22T00:00:00.0000000001Z",
    };
    assert_eq!(trust_tier(generated, &[human]), TrustTier::Unverified);
    for at in [
        "2026-11-22T00:00:00.00000000020Z",
        "2026-11-22T01:00:00.000000000200+01:00",
        "2026-11-22T00:00:00.0000000002001Z",
        "2026-11-22T00:00:00.0000000003Z",
    ] {
        assert_eq!(
            trust_tier(generated, &[Verification { at, ..human }]),
            TrustTier::HumanReviewed,
            "{at}"
        );
    }
    // Tail comparison also works when the ninth fractional digit is nonzero.
    let generated = Some(Generation {
        at: Some("2026-11-22T00:00:00.1234567891Z"),
    });
    assert_eq!(
        trust_tier(
            generated,
            &[Verification {
                at: "2026-11-22T00:00:00.12345678909Z",
                ..human
            }]
        ),
        TrustTier::Unverified
    );
}
