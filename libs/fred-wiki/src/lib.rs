// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Pure native Wiki page formatting, based on OKF 0.3 at 527e81a.
//! Reading and editing preserve YAML values; native write policy is explicit.
//! Catalogue metadata, authorization and the current time belong to the caller.

mod metadata;

pub use metadata::{Freshness, Generation, TrustTier, Verification, freshness, trust_tier};
use std::borrow::Cow;

pub use oneyaml::{Document, EditError, MappingRef, NodeRef};
use oneyaml::{Limits, Settings};

/// Same scalar-value ceiling as the catalogue's ordinary Wiki page constraint.
pub const MAX_PAGE_CHARS: usize = 100_000;
pub const MAX_DESCRIPTION_CHARS: usize = 300;
pub const NATIVE_PAGE_TYPES: &[&str] = &[
    "topic",
    "procedure",
    "decision",
    "reference",
    "source",
    "hub",
    "untyped",
];

/// Pure searchable fields. The caller owns title, identity, language and ranking.
#[derive(Debug, PartialEq, Eq)]
pub struct IndexDocument<'a> {
    pub page_type: Cow<'a, str>,
    pub description: Option<Cow<'a, str>>,
    pub tags: Vec<Cow<'a, str>>,
    pub aliases: Vec<Cow<'a, str>>,
    pub read_when: Option<Cow<'a, str>>,
    pub body: &'a str,
}

pub fn index_document<'a>(page: &'a Page<'_>) -> IndexDocument<'a> {
    let authored = page.authored();
    IndexDocument {
        page_type: authored.page_type.unwrap_or(Cow::Borrowed("untyped")),
        description: authored.description,
        tags: authored.tags,
        aliases: authored.aliases,
        read_when: authored.read_when,
        body: page.body(),
    }
}

#[derive(Debug, thiserror::Error)]
#[error("{path}: {message}")]
pub struct Error {
    pub path: String,
    pub message: String,
}

fn invalid(path: &str, message: impl Into<String>) -> Error {
    Error {
        path: path.into(),
        message: message.into(),
    }
}

/// Borrowed original content and its optional YAML mapping. No body normalization.
#[derive(Debug)]
pub struct Page<'a> {
    original: &'a str,
    body: &'a str,
    header: Option<Document>,
    newline: &'static str,
}

impl<'a> Page<'a> {
    pub fn parse(content: &'a str) -> Result<Self, Error> {
        check_content(content)?;
        let (first, rest) = line(content);
        if first != "---" {
            return Ok(Self {
                original: content,
                body: content,
                header: None,
                newline: "\n",
            });
        }
        let newline = if content.starts_with("---\r\n") {
            "\r\n"
        } else {
            "\n"
        };
        let mut remaining = rest;
        while !remaining.is_empty() {
            let (current, next) = line(remaining);
            if current == "---" {
                let yaml = &rest[..rest.len() - remaining.len()];
                let header =
                    Document::parse_with(yaml, &Settings::new().limits(Limits::untrusted()))
                        .map_err(|error| invalid("$", error.to_string()))?;
                // Typed string reads can allocate once per alias (escaped scalars).
                // Check the library expansion budgets without building another tree.
                header
                    .deserialize::<serde::de::IgnoredAny>()
                    .map_err(|error| invalid("$", error.to_string()))?;
                if header.root().and_then(NodeRef::as_mapping).is_none() {
                    return Err(invalid("$", "frontmatter must be a YAML mapping"));
                }
                return Ok(Self {
                    original: content,
                    body: next,
                    header: Some(header),
                    newline,
                });
            }
            remaining = next;
        }
        Err(invalid("$", "unclosed frontmatter"))
    }

    pub fn body(&self) -> &'a str {
        self.body
    }

    pub fn header(&self) -> Option<&Document> {
        self.header.as_ref()
    }

    /// Tolerant OKF reading: empty values are absent, lists accept singletons,
    /// and source entries missing their required resource are ignored.
    /// The original mapping retains every value, including malformed fields.
    pub fn authored(&self) -> Authored<'_> {
        let field = |name| self.header.as_ref().and_then(|map| present(map.get(name)));
        Authored {
            page_type: field("type").and_then(NodeRef::as_str),
            description: field("description").and_then(NodeRef::as_str),
            tags: strings(field("tags")),
            sources: items(field("sources"))
                .iter()
                .filter_map(|value| {
                    let fields = value.as_mapping()?;
                    let resource = present(fields.get("resource"))?.as_str()?;
                    Some(Source { resource, fields })
                })
                .collect(),
            stale_after: field("stale_after"),
            aliases: strings(field("x-fred-aliases")),
            read_when: field("x-fred-read-when").and_then(NodeRef::as_str),
        }
    }

    /// Validate a native write, separately from tolerant reading/import handling.
    /// Missing type is allowed; agent-specific requirements belong to the caller.
    pub fn validate_native(&self) -> Result<(), Error> {
        let Some(header) = self
            .header
            .as_ref()
            .and_then(Document::root)
            .and_then(NodeRef::as_mapping)
        else {
            return Ok(());
        };
        for name in ["generated", "verified", "status", "superseded_by", "title"] {
            if header.get(name).is_some() {
                return Err(invalid(name, "field is derived from the catalogue"));
            }
        }
        if let Some(kind) = string_field(header, "type", "type")?
            && !NATIVE_PAGE_TYPES.contains(&kind.as_ref())
        {
            return Err(invalid("type", "unknown native page type"));
        }
        if let Some(description) = string_field(header, "description", "description")?
            && (description.chars().count() > MAX_DESCRIPTION_CHARS
                || description.contains(['\n', '\r', '\u{85}', '\u{2028}', '\u{2029}']))
        {
            return Err(invalid(
                "description",
                "must be one line of at most 300 Unicode scalar values",
            ));
        }
        string_field(header, "x-fred-read-when", "x-fred-read-when")?;
        for name in ["tags", "x-fred-aliases"] {
            for (index, item) in items(present(header.get(name))).into_iter().enumerate() {
                if item.as_str().is_none() {
                    return Err(invalid(&format!("{name}[{index}]"), "must be a string"));
                }
            }
        }
        timestamp_field(header, "stale_after", "stale_after")?;
        for (index, item) in items(present(header.get("sources")))
            .into_iter()
            .enumerate()
        {
            let path = format!("sources[{index}]");
            let fields = item
                .as_mapping()
                .ok_or_else(|| invalid(&path, "must be a mapping"))?;
            if string_field(fields, "resource", &format!("{path}.resource"))?.is_none() {
                return Err(invalid(
                    &format!("{path}.resource"),
                    "source resource is required",
                ));
            }
            for name in ["id", "title", "author"] {
                string_field(fields, name, &format!("{path}.{name}"))?;
            }
            timestamp_field(fields, "last_modified", &format!("{path}.last_modified"))?;
        }
        Ok(())
    }

    /// Edit the retained YAML syntax tree with the library's lossless editor.
    /// Untouched values keep their original text, including unknown numbers/tags.
    /// Changing a referenced anchor is refused to protect values shared by aliases.
    /// This is a format operation: call `validate_native` before native writes.
    pub fn edit_header(
        &self,
        edit: impl FnOnce(&mut Document) -> Result<(), EditError>,
    ) -> Result<String, Error> {
        let mut header = match &self.header {
            Some(header) => header.clone(),
            None => Document::parse_with("{}\n", &Settings::new().limits(Limits::untrusted()))
                .map_err(|error| invalid("$", error.to_string()))?,
        };
        let original_yaml = header.to_string();
        edit(&mut header).map_err(|error| invalid("$", error.to_string()))?;
        let mut yaml = header.to_string();
        if yaml == original_yaml {
            return Ok(self.original.to_owned());
        }
        if let Some(original) = &self.header {
            preserve_shared_values(original, &header)?;
        }
        let newline = self.newline;
        if !yaml.ends_with('\n') {
            yaml.push_str(newline);
        }
        let result = format!("---{newline}{yaml}---{newline}{}", self.body);
        let edited = Page::parse(&result)?;
        if edited.body != self.body {
            return Err(invalid("$", "header edit changed body boundaries"));
        }
        Ok(result)
    }
}

#[derive(Debug)]
pub struct Authored<'a> {
    pub page_type: Option<Cow<'a, str>>,
    pub description: Option<Cow<'a, str>>,
    pub tags: Vec<Cow<'a, str>>,
    pub sources: Vec<Source<'a>>,
    /// Raw value allows freshness to distinguish malformed dates from absent ones.
    pub stale_after: Option<NodeRef<'a>>,
    pub aliases: Vec<Cow<'a, str>>,
    pub read_when: Option<Cow<'a, str>>,
}

#[derive(Debug)]
pub struct Source<'a> {
    pub resource: Cow<'a, str>,
    /// Includes unknown fields and known revision references without rewriting.
    pub fields: MappingRef<'a>,
}

// Walk syntax nodes, never expanded aliases. Library handles identify referenced
// anchors across a clone; refusing changes avoids silently changing other fields.
fn preserve_shared_values(original: &Document, edited: &Document) -> Result<(), Error> {
    let mut nodes: Vec<_> = original.root().into_iter().collect();
    while let Some(node) = nodes.pop() {
        if node.alias_name().is_some() {
            continue;
        }
        if node.anchor().is_some()
            && !original
                .aliases_of(node.id())
                .map_err(|error| invalid("$", error.to_string()))?
                .is_empty()
            && !edited
                .node(node.id())
                .is_ok_and(|after| after.text() == node.text())
        {
            return Err(invalid(
                "$",
                "cannot change an anchor referenced by aliases",
            ));
        }
        if let Some(mapping) = node.as_mapping() {
            for (key, value) in mapping.iter() {
                nodes.extend([key, value]);
            }
        } else if let Some(sequence) = node.as_sequence() {
            nodes.extend(sequence.iter());
        }
    }
    Ok(())
}

fn check_content(content: &str) -> Result<(), Error> {
    if content.contains('\0') || content.chars().count() > MAX_PAGE_CHARS {
        return Err(invalid(
            "$",
            "page exceeds 100000 Unicode scalar values or contains NUL",
        ));
    }
    Ok(())
}

// Slice at byte boundaries, consuming only the delimiter's line terminator.
fn line(text: &str) -> (&str, &str) {
    match text.split_once('\n') {
        Some((head, tail)) => (head.strip_suffix('\r').unwrap_or(head), tail),
        None => (text, ""),
    }
}

pub(crate) fn present(value: Option<NodeRef<'_>>) -> Option<NodeRef<'_>> {
    value.filter(|value| {
        !value.is_null()
            && !value.as_str().is_some_and(|text| text.is_empty())
            && !value.as_sequence().is_some_and(|items| items.is_empty())
    })
}

fn items(value: Option<NodeRef<'_>>) -> Vec<NodeRef<'_>> {
    match value {
        None => Vec::new(),
        Some(value) => match value.as_sequence() {
            Some(items) => items.iter().collect(),
            None => vec![value],
        },
    }
}

fn strings(value: Option<NodeRef<'_>>) -> Vec<Cow<'_, str>> {
    items(value)
        .into_iter()
        .filter_map(NodeRef::as_str)
        .collect()
}

fn string_field<'a>(
    fields: MappingRef<'a>,
    name: &str,
    path: &str,
) -> Result<Option<Cow<'a, str>>, Error> {
    present(fields.get(name))
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| invalid(path, "must be a string"))
        })
        .transpose()
}

fn timestamp_field(fields: MappingRef<'_>, name: &str, path: &str) -> Result<(), Error> {
    if let Some(value) = present(fields.get(name))
        && value
            .as_str()
            .as_deref()
            .and_then(metadata::timestamp)
            .is_none()
    {
        return Err(invalid(path, "must be an RFC 3339 date or date-time"));
    }
    Ok(())
}
