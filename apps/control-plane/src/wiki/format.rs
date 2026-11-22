// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! HTTP format bridge. Catalogue access, candidate selection and publication stay
//! in governance; this module interprets native Wiki content for HTTP.
#[cfg(test)]
use super::WikiConflict;
use super::{Error, Result, WikiPageDetail, invalid, store::ProposalRow};
use chrono::{DateTime, FixedOffset, Utc};
use fred_wiki::{Freshness, Page};
use serde::Serialize;
use utoipa::ToSchema;

#[derive(Debug, Serialize, ToSchema)]
pub struct WikiFormat {
    /// Exact source prefix, including delimiters and line endings. Never rebuild YAML from fields.
    pub frontmatter_prefix: String,
    pub body_md: String,
    pub page_type: String,
    pub description: Option<String>,
    pub tags: Vec<String>,
    pub sources: Vec<WikiSource>,
    pub stale_after: Option<String>,
    pub aliases: Vec<String>,
    pub read_when: Option<String>,
    pub freshness: WikiFreshness,
    /// Publication is not content confirmation. Empty until confirmations exist.
    pub verified: Vec<WikiVerification>,
    pub trust: WikiTrust,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct WikiSource {
    pub resource: String,
    pub id: Option<String>,
    pub title: Option<String>,
    pub author: Option<String>,
    pub last_modified: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct WikiVerification {
    pub by: String,
    pub at: String,
}

#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum WikiTrust {
    Unverified,
}

#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum WikiFreshness {
    Unspecified,
    Fresh,
    Stale,
    Malformed,
}

pub(super) fn native_type(value: &str) -> bool {
    fred_wiki::NATIVE_PAGE_TYPES.contains(&value)
}

/// The native profile, without actor policy: shared by writes and reads.
fn native(text: &str) -> std::result::Result<Page<'_>, fred_wiki::Error> {
    let page = Page::parse(text)?;
    page.validate_native()?;
    Ok(page)
}

fn parse(text: &str, agent: bool) -> Result<Page<'_>> {
    let page = native(text).map_err(|error| invalid(&error.to_string()))?;
    if agent && page.authored().page_type.is_none() {
        return Err(invalid(
            "type: an agent proposal requires an explicit native type",
        ));
    }
    Ok(page)
}

pub(super) fn validate(text: &str, agent: bool) -> Result<()> {
    parse(text, agent).map(|_| ())
}

/// The candidate and its provenance were selected under the existing catalogue locks.
pub(super) fn revision(row: &ProposalRow) -> Result<()> {
    if row.entry_kind == "page" {
        validate(&row.content_md, row.agent_instance_id.is_some())?;
    }
    Ok(())
}

/// Reads never apply write policy: stored text stays readable and repairable.
fn view(
    text: &str,
    now: DateTime<FixedOffset>,
) -> std::result::Result<WikiFormat, fred_wiki::Error> {
    let page = native(text)?;
    let authored = page.authored();
    Ok(WikiFormat {
        frontmatter_prefix: text[..text.len() - page.body().len()].into(),
        body_md: page.body().into(),
        page_type: authored.page_type.as_deref().unwrap_or("untyped").into(),
        description: authored.description.map(|value| value.into_owned()),
        tags: authored
            .tags
            .into_iter()
            .map(|value| value.into_owned())
            .collect(),
        sources: authored
            .sources
            .into_iter()
            .map(|source| {
                let field = |name| {
                    source
                        .fields
                        .get(name)
                        .and_then(|value| value.as_str())
                        .filter(|value| !value.is_empty())
                        .map(|value| value.into_owned())
                };
                WikiSource {
                    resource: source.resource.into_owned(),
                    id: field("id"),
                    title: field("title"),
                    author: field("author"),
                    last_modified: field("last_modified"),
                }
            })
            .collect(),
        stale_after: authored
            .stale_after
            .and_then(|value| value.as_str())
            .map(|value| value.into_owned()),
        aliases: authored
            .aliases
            .into_iter()
            .map(|value| value.into_owned())
            .collect(),
        read_when: authored.read_when.map(|value| value.into_owned()),
        freshness: match fred_wiki::freshness(authored.stale_after, now) {
            Freshness::Unspecified => WikiFreshness::Unspecified,
            Freshness::Fresh => WikiFreshness::Fresh,
            Freshness::Stale => WikiFreshness::Stale,
            Freshness::Malformed => WikiFreshness::Malformed,
        },
        verified: vec![],
        trust: WikiTrust::Unverified,
    })
}

/// Detail responses only, after releasing the catalogue transaction. Nonconforming
/// stored text keeps `content_md` as its source and states why it has no view.
pub(super) fn enrich(detail: &mut WikiPageDetail) {
    if detail.page.kind == "page" {
        match view(&detail.content_md, Utc::now().fixed_offset()) {
            Ok(format) => detail.format = Some(format),
            Err(error) => detail.format_error = Some(error.to_string()),
        }
    }
}

/// Reuse the same snapshot for conflict body, opaque prefix and revision identity.
/// A conflict stays a conflict: without a view, the client rebases on raw text.
pub(super) fn error(error: Error) -> Error {
    match error {
        Error::Stale(mut conflict) if conflict.current_kind == "page" => {
            conflict.current_format =
                view(&conflict.current_content_md, Utc::now().fixed_offset()).ok();
            Error::Stale(conflict)
        }
        other => other,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_policy_and_field_paths() {
        assert!(validate("", false).is_ok());
        assert!(
            validate("no header", true)
                .unwrap_err()
                .to_string()
                .contains("type:")
        );
        for field in ["generated", "verified", "status", "superseded_by", "title"] {
            assert!(
                validate(&format!("---\n{field}: null\n---\nbody"), false)
                    .unwrap_err()
                    .to_string()
                    .contains(field)
            );
        }
        assert!(validate("---\ntype: topic\n---\nbody", true).is_ok());
        assert!(validate("---\ntype: imported\n---\nbody", false).is_err());
        assert!(
            validate("---\ntags: [2]\n---\nbody", false)
                .unwrap_err()
                .to_string()
                .contains("tags[0]")
        );
        assert!(validate("---\nunclosed", false).is_err());
    }

    #[test]
    fn view_preserves_source_and_never_invents_trust() {
        let now = DateTime::parse_from_rfc3339("2026-11-22T12:00:00Z").unwrap();
        for newline in ["\n", "\r\n"] {
            let prefix = format!(
                "---{newline}type: topic{newline}stale_after: 2026-11-21{newline}x-extension:{newline}  huge: 123456789012345678901234567890{newline}  exact: 0.123456789012345678901234567890{newline}---{newline}"
            );
            let text = format!("{prefix}# Body\r\n\n");
            let view = view(&text, now).unwrap();
            assert_eq!(view.frontmatter_prefix, prefix);
            assert_eq!(view.body_md, "# Body\r\n\n");
            assert_eq!(format!("{}{}", view.frontmatter_prefix, view.body_md), text);
            assert!(view.verified.is_empty());
            assert!(matches!(view.trust, WikiTrust::Unverified));
            assert!(matches!(view.freshness, WikiFreshness::Stale));
        }
    }

    #[test]
    fn header_closed_at_eof_keeps_bytes_and_accepts_a_separated_new_body() {
        let now = DateTime::parse_from_rfc3339("2026-11-22T12:00:00Z").unwrap();
        for newline in ["\n", "\r\n"] {
            let prefix = format!("---{newline}type: topic{newline}---");
            let empty = view(&prefix, now).unwrap();
            assert_eq!(empty.frontmatter_prefix, prefix);
            assert_eq!(empty.body_md, "");
            let edited = view(&format!("{prefix}{newline}Body"), now).unwrap();
            assert_eq!(edited.frontmatter_prefix, format!("{prefix}{newline}"));
            assert_eq!(edited.body_md, "Body");
        }
    }

    #[test]
    fn only_ordinary_details_have_a_view_and_invalid_content_stays_readable() {
        let mut detail = WikiPageDetail {
            content_md: "---\nverified: null\n---\n".into(),
            ..Default::default()
        };
        for kind in ["rules", "file"] {
            detail.page.kind = kind.into();
            enrich(&mut detail);
            assert!(detail.format.is_none() && detail.format_error.is_none());
        }
        detail.page.kind = "page".into();
        enrich(&mut detail);
        assert!(detail.format.is_none());
        assert!(detail.format_error.take().unwrap().starts_with("verified:"));
        // Read never applies the agent write policy.
        detail.content_md = "plain agent text".into();
        detail.page.agent_instance_id = Some(uuid::Uuid::nil());
        enrich(&mut detail);
        assert!(detail.format_error.is_none());
        assert_eq!(detail.format.unwrap().page_type, "untyped");
    }

    #[test]
    fn a_conflict_on_nonconforming_text_remains_a_conflict() {
        let conflict = WikiConflict {
            detail: "changed",
            current_revision_id: None,
            current_content_md: "---\nstatus: null\n---\nbody".into(),
            current_format: None,
            current_kind: "page".into(),
        };
        let Error::Stale(conflict) = error(Error::Stale(Box::new(conflict))) else {
            panic!("a stale write must stay a conflict");
        };
        assert!(conflict.current_format.is_none());
    }
}
