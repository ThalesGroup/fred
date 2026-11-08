// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::BTreeMap;

use serde::Deserialize;
use sha2::{Digest, Sha256};

use super::PackageSummary;
use crate::error::{AppError, AppResult};

pub type Files = BTreeMap<String, String>;
pub const MAX_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_SKILLS: usize = 64;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Frontmatter {
    name: String,
    description: String,
    license: Option<String>,
    compatibility: Option<String>,
    #[serde(default)]
    metadata: BTreeMap<String, String>,
    #[serde(rename = "allowed-tools")]
    allowed_tools: Option<String>,
}

fn invalid(message: &str) -> AppError {
    AppError::Unprocessable(message.into())
}

pub fn valid_name(name: &str) -> bool {
    (1..=64).contains(&name.len())
        && name.split('-').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        })
}

/// Validate once at the content owner. Optional tool declarations never grant tools.
pub fn validate(name: &str, files: &Files, builtin: bool) -> AppResult<PackageSummary> {
    if !valid_name(name)
        || files.len() > 128
        || files.values().map(String::len).sum::<usize>() > MAX_BYTES
    {
        return Err(invalid("Invalid skill name or package bounds"));
    }
    for (path, content) in files {
        let parts: Vec<_> = path.split('/').collect();
        if parts.len() > 8
            || parts
                .iter()
                .any(|p| p.is_empty() || *p == "." || *p == "..")
            || path.contains(['\\', '\0'])
            || content.contains('\0')
            || content.len() > 65536
            || ![".md", ".txt", ".json", ".yaml", ".yml", ".csv"]
                .iter()
                .any(|suffix| path.ends_with(suffix))
        {
            return Err(invalid(
                "Skill resources must be bounded relative UTF-8 text files; binary resources and scripts are unsupported",
            ));
        }
    }
    let document = files
        .get("SKILL.md")
        .ok_or_else(|| invalid("SKILL.md is required"))?;
    let mut lines = document.lines();
    if lines.next() != Some("---") {
        return Err(invalid("SKILL.md requires YAML frontmatter"));
    }
    let mut yaml = String::new();
    let mut closed = false;
    for line in lines {
        if line == "---" {
            closed = true;
            break;
        }
        yaml.push_str(line);
        yaml.push('\n');
    }
    if !closed {
        return Err(invalid("Unclosed skill frontmatter"));
    }
    // Deserialize scalar types without YAML's permissive String coercion.
    let front: Frontmatter = serde_yaml_ng::from_str::<serde_json::Value>(&yaml)
        .ok().and_then(|value| serde_json::from_value(value).ok()).ok_or_else(|| {
        invalid(
            "Invalid Agent Skills frontmatter; Fred extensions belong in string-valued metadata",
        )
    })?;
    if front.name != name
        || front.description.trim().is_empty()
        || front.description.chars().count() > 1024
        || front
            .compatibility
            .as_ref()
            .is_some_and(|v| v.is_empty() || v.chars().count() > 500)
    {
        return Err(invalid("Invalid skill name, description or compatibility"));
    }
    let flag = |key: &str, default: bool| -> AppResult<bool> {
        match front.metadata.get(key).map(String::as_str) {
            None => Ok(default),
            Some("true") => Ok(true),
            Some("false") => Ok(false),
            _ => Err(invalid(
                "Fred invocation controls must be the strings true or false",
            )),
        }
    };
    let hint = front.metadata.get("fred-argument-hint").cloned();
    if hint
        .as_ref()
        .is_some_and(|v| v.trim().is_empty() || v.chars().count() > 256)
    {
        return Err(invalid("Invalid Fred argument hint"));
    }
    // Retained verbatim in SKILL.md; these are declarations, not runtime authority.
    let _ = (front.license, front.allowed_tools);
    Ok(PackageSummary {
        name: front.name.clone(),
        description: front.description.trim().to_owned(),
        argument_hint: hint.map(|v| v.trim().to_owned()),
        builtin,
        user_invocable: flag("fred-user-invocable", true)?,
        disable_model_invocation: flag("fred-disable-model-invocation", false)?,
    })
}

pub fn revision(files: &Files) -> String {
    let mut digest = Sha256::new();
    for (path, content) in files {
        digest.update(path.as_bytes());
        digest.update([0]);
        digest.update(content.as_bytes());
        digest.update([0]);
    }
    format!("{:x}", digest.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn supplied_packages_are_valid_and_preserve_invocation_controls() {
        let packages = crate::skills::defaults::packages();
        assert_eq!(packages.len(), 7);
        for (name, files) in packages {
            let summary = validate(name, &files, true).unwrap();
            assert!(summary.builtin);
            assert_eq!(
                summary.disable_model_invocation,
                matches!(name, "grill-me" | "meeting-minutes")
            );
            assert_eq!(
                summary.user_invocable,
                matches!(name, "grill-me" | "meeting-minutes" | "graph")
            );
            assert_eq!(revision(&files).len(), 64);
        }
    }

    #[test]
    fn reject_invalid_packages_without_changing_tool_authority() {
        let standard = Files::from([("SKILL.md".into(), "---\nname: example\ndescription: Use for examples\nallowed-tools: Bash\n---\nInstructions".into())]);
        assert!(validate("example", &standard, false).is_ok());
        let spaced = Files::from([("SKILL.md".into(), "---\nname: example\ndescription: '  Example  '\nmetadata:\n  fred-argument-hint: '  [file]  '\n---\nBody".into())]);
        let summary = validate("example", &spaced, false).unwrap();
        assert_eq!(summary.description, "Example");
        assert_eq!(summary.argument_hint.as_deref(), Some("[file]"));
        for path in [
            "../private.md",
            "/private.md",
            "references/../private.md",
            "scripts/run.py",
            "assets/image.png",
        ] {
            let mut bad = standard.clone();
            bad.insert(path.into(), "text".into());
            assert!(validate("example", &bad, false).is_err());
        }
        for header in [
            "name: other\ndescription: ok",
            "name: example\ndescription: ''",
            "name: example\ndescription: ok\nuser-invocable: false",
            "name: example\ndescription: ok\nmetadata:\n  fred-user-invocable: maybe",
            "name: example\ndescription: ok\nmetadata:\n  fred-user-invocable: false",
            "name: example\ndescription: 123",
            "name: example\ndescription: ok\nmetadata:\n  author: 123",
        ] {
            let bad = Files::from([("SKILL.md".into(), format!("---\n{header}\n---\nBody"))]);
            assert!(validate("example", &bad, false).is_err());
        }
        let mut changed = standard.clone();
        changed.insert("references/example.md".into(), "reference".into());
        assert_ne!(revision(&standard), revision(&changed));
    }
}
