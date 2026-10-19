// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! The sole provisioning wire format. No extraction or legacy conversion occurs here.
use crate::{
    domain::{Role, SpaceKind},
    roles::PlatformRole,
};
use serde::Deserialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Cursor, Read},
};

pub const MAX_ARCHIVE: usize = 50 * 1024 * 1024;
const MAX_EXPANDED: usize = 100 * 1024 * 1024;
const FILES: [&str; 5] = [
    "manifest.json",
    "users.json",
    "organizations.json",
    "teams.json",
    "projects.json",
];

#[derive(Debug, thiserror::Error)]
pub enum InputError {
    #[error("not_yet_supported")]
    Unsupported,
    #[error("invalid provisioning ZIP or declaration")]
    Invalid,
    #[error("provisioning bundle exceeds size limit")]
    TooLarge,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    format_version: u64,
    users_schema_version: u64,
    source_platform: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct User {
    pub username: String,
    pub email: Option<String>,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub password: Option<String>,
    #[serde(default)]
    pub platform_roles: Vec<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawSpace {
    #[serde(rename = "ref")]
    reference: String,
    name: String,
    roles: BTreeMap<String, Vec<Role>>,
    organization: Option<String>,
    team: Option<String>,
}
pub(crate) struct SpaceDeclaration {
    pub name: String,
    pub kind: SpaceKind,
    pub parent: Option<usize>,
    pub roles: BTreeMap<String, Vec<Role>>,
}
pub(crate) struct Entry {
    pub identity: User,
    pub platform: BTreeSet<PlatformRole>,
}
/// Password-bearing input deliberately has no Debug or Serialize implementation.
pub struct Bundle {
    pub(crate) users: Vec<Entry>,
    /// Parent-first order; parent indices refer only to this bundle.
    pub(crate) spaces: Vec<SpaceDeclaration>,
}
fn name(value: &str) -> bool {
    !value.trim().is_empty() && !value.chars().any(char::is_control)
}
impl Bundle {
    /// CPU-bound parsing; async entrypoints call this through spawn_blocking.
    pub fn parse(bytes: &[u8]) -> Result<Self, InputError> {
        Self::parse_limited(bytes, MAX_ARCHIVE, MAX_EXPANDED)
    }
    fn parse_limited(
        bytes: &[u8],
        archive_limit: usize,
        expanded_limit: usize,
    ) -> Result<Self, InputError> {
        use InputError::*;
        if bytes.len() > archive_limit {
            return Err(TooLarge);
        }
        if bytes
            .iter()
            .find(|b| !b.is_ascii_whitespace())
            .is_some_and(|b| *b == b'{' || *b == b'[')
        {
            return Err(Unsupported);
        }
        // Bound central-directory allocation and reject duplicates before zip's name map
        // can collapse them. ZIP64/multidisk are outside this five-small-files format.
        let count = check_directory(bytes)?;
        let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(|_| Invalid)?;
        if archive.len() != count {
            return Err(Invalid);
        }
        let mut remaining = expanded_limit;
        let mut files = BTreeMap::new();
        for i in 0..archive.len() {
            let mut file = archive.by_index(i).map_err(|_| Invalid)?;
            let filename = file.name().map_err(|_| Invalid)?.into_owned();
            if !file.is_file() || file.encrypted() {
                return Err(Invalid);
            }
            if !matches!(
                file.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            ) {
                return Err(Unsupported);
            }
            let mut data = Vec::new();
            (&mut file)
                .take(remaining as u64 + 1)
                .read_to_end(&mut data)
                .map_err(|_| Invalid)?;
            if data.len() > remaining {
                return Err(TooLarge);
            }
            remaining -= data.len();
            files.insert(filename, data);
        }
        let manifest_value: serde_json::Value = json(files.get("manifest.json").ok_or(Invalid)?)?;
        if manifest_value
            .get("format_version")
            .and_then(|v| v.as_u64())
            .is_some_and(|v| v != 2)
        {
            return Err(Unsupported);
        }
        let manifest: Manifest = serde_json::from_value(manifest_value).map_err(|_| Invalid)?;
        if manifest.format_version != 2
            || manifest.users_schema_version != 2
            || manifest.source_platform != "swift"
        {
            return Err(Unsupported);
        }
        if FILES.iter().any(|f| !files.contains_key(*f)) {
            return Err(Invalid);
        }
        let raw: Vec<User> = json(&files["users.json"])?;
        let mut names = BTreeSet::new();
        let mut users = Vec::new();
        for user in raw {
            if !name(&user.username)
                || user.username.trim() != user.username
                || user.username.to_lowercase() != user.username
                || !names.insert(user.username.clone())
            {
                return Err(Invalid);
            }
            let platform = user
                .platform_roles
                .iter()
                .map(|r| PlatformRole::parse(r).ok_or(Invalid))
                .collect::<Result<_, _>>()?;
            users.push(Entry {
                identity: user,
                platform,
            });
        }
        let mut spaces: Vec<SpaceDeclaration> = Vec::new();
        let mut references: BTreeMap<String, usize> = BTreeMap::new();
        let mut siblings = BTreeSet::new();
        for (file, kind) in [
            ("organizations.json", SpaceKind::Organization),
            ("teams.json", SpaceKind::Team),
            ("projects.json", SpaceKind::Project),
        ] {
            let raw: Vec<RawSpace> = json(&files[file])?;
            if kind == SpaceKind::Organization && raw.is_empty() {
                return Err(Invalid);
            }
            for raw in raw {
                if !name(&raw.reference)
                    || !crate::domain::valid_space_name(&raw.name)
                    || references.contains_key(&raw.reference)
                {
                    return Err(Invalid);
                }
                let parent_ref = match kind {
                    SpaceKind::Organization if raw.organization.is_none() && raw.team.is_none() => {
                        None
                    }
                    SpaceKind::Team if raw.team.is_none() => Some(raw.organization.ok_or(Invalid)?),
                    SpaceKind::Project if raw.organization.is_none() => {
                        Some(raw.team.ok_or(Invalid)?)
                    }
                    _ => return Err(Invalid),
                };
                let parent = parent_ref
                    .as_ref()
                    .map(|r| references.get(r).copied().ok_or(Invalid))
                    .transpose()?;
                if let Some(p) = parent {
                    let expected = if kind == SpaceKind::Team {
                        SpaceKind::Organization
                    } else {
                        SpaceKind::Team
                    };
                    if spaces[p].kind != expected {
                        return Err(Invalid);
                    }
                }
                if !siblings.insert((parent, raw.name.clone())) {
                    return Err(Invalid);
                }
                let mut roles = raw.roles;
                for (subject, grants) in &mut roles {
                    if !names.contains(subject)
                        || (kind != SpaceKind::Organization
                            && (grants.contains(&Role::OrganizationOwner)
                                || grants.contains(&Role::PersonalSpaceCreator)))
                    {
                        return Err(Invalid);
                    }
                    let mut unique = Vec::new();
                    for r in grants.drain(..) {
                        if !unique.contains(&r) {
                            unique.push(r);
                        }
                    }
                    *grants = unique;
                }
                references.insert(raw.reference.clone(), spaces.len());
                spaces.push(SpaceDeclaration {
                    name: raw.name,
                    kind,
                    parent,
                    roles,
                });
            }
        }
        Ok(Self { users, spaces })
    }
}

fn check_directory(bytes: &[u8]) -> Result<usize, InputError> {
    use InputError::*;
    let u16_at = |offset: usize| -> Result<usize, InputError> {
        Ok(u16::from_le_bytes(
            bytes
                .get(offset..offset + 2)
                .ok_or(Invalid)?
                .try_into()
                .map_err(|_| Invalid)?,
        ) as usize)
    };
    let u32_at = |offset: usize| -> Result<usize, InputError> {
        Ok(u32::from_le_bytes(
            bytes
                .get(offset..offset + 4)
                .ok_or(Invalid)?
                .try_into()
                .map_err(|_| Invalid)?,
        ) as usize)
    };
    let end = (bytes.len().saturating_sub(65557)..bytes.len().saturating_sub(21))
        .rev()
        .find(|i| {
            bytes.get(*i..*i + 4) == Some(b"PK\x05\x06")
                && u16_at(*i + 20).is_ok_and(|n| *i + 22 + n == bytes.len())
        })
        .ok_or(Invalid)?;
    if u16_at(end + 4)? != 0 || u16_at(end + 6)? != 0 {
        return Err(Unsupported);
    }
    let count = u16_at(end + 10)?;
    if count != u16_at(end + 8)? {
        return Err(Invalid);
    }
    if count > FILES.len() {
        return Err(Unsupported);
    }
    let mut at = u32_at(end + 16)?;
    if at.checked_add(u32_at(end + 12)?) != Some(end) {
        return Err(Invalid);
    }
    let mut names = BTreeSet::new();
    for _ in 0..count {
        if bytes.get(at..at + 4) != Some(b"PK\x01\x02") {
            return Err(Invalid);
        }
        let len = u16_at(at + 28)?;
        let filename = std::str::from_utf8(bytes.get(at + 46..at + 46 + len).ok_or(Invalid)?)
            .map_err(|_| Invalid)?;
        if filename.contains(['/', '\\']) || !names.insert(filename) {
            return Err(Invalid);
        }
        if !FILES.contains(&filename) {
            return Err(Unsupported);
        }
        // A local header must describe the same entry as the directory. zip uses
        // directory names, so check this before accepting a disguised local path.
        let local = u32_at(at + 42)?;
        if bytes.get(local..local + 4) != Some(b"PK\x03\x04")
            || u16_at(local + 26)? != len
            || bytes.get(local + 30..local + 30 + len) != Some(filename.as_bytes())
            || u16_at(local + 6)? != u16_at(at + 8)?
            || u16_at(local + 8)? != u16_at(at + 10)?
        {
            return Err(Invalid);
        }
        at += 46 + len + u16_at(at + 30)? + u16_at(at + 32)?;
        if at > end {
            return Err(Invalid);
        }
    }
    if at != end {
        return Err(Invalid);
    }
    Ok(count)
}

// Value's default map decoder overwrites duplicate keys. Check every nested object
// while decoding, then deserialize the typed declaration without logging its contents.
struct Unique(serde_json::Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = Unique;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("JSON with unique keys")
            }
            fn visit_map<M: serde::de::MapAccess<'de>>(
                self,
                mut map: M,
            ) -> Result<Unique, M::Error> {
                let mut result = serde_json::Map::new();
                while let Some((key, Unique(value))) = map.next_entry::<String, Unique>()? {
                    if result.insert(key, value).is_some() {
                        return Err(serde::de::Error::custom("duplicate key"));
                    }
                }
                Ok(Unique(result.into()))
            }
            fn visit_seq<S: serde::de::SeqAccess<'de>>(
                self,
                mut seq: S,
            ) -> Result<Unique, S::Error> {
                let mut result = Vec::new();
                while let Some(Unique(value)) = seq.next_element()? {
                    result.push(value);
                }
                Ok(Unique(result.into()))
            }
            fn visit_bool<E: serde::de::Error>(self, v: bool) -> Result<Unique, E> {
                Ok(Unique(v.into()))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> Result<Unique, E> {
                Ok(Unique(v.into()))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> Result<Unique, E> {
                Ok(Unique(v.into()))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> Result<Unique, E> {
                Ok(Unique(v.into()))
            }
            fn visit_str<E: serde::de::Error>(self, v: &str) -> Result<Unique, E> {
                Ok(Unique(v.into()))
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Unique, E> {
                Ok(Unique(serde_json::Value::Null))
            }
        }
        d.deserialize_any(Visitor)
    }
}
fn json<T: serde::de::DeserializeOwned>(bytes: &[u8]) -> Result<T, InputError> {
    let Unique(value) = serde_json::from_slice(bytes).map_err(|_| InputError::Invalid)?;
    serde_json::from_value(value).map_err(|_| InputError::Invalid)
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    fn files() -> BTreeMap<String, Vec<u8>> {
        [
            ("manifest.json", r#"{"format_version":2,"users_schema_version":2,"source_platform":"swift"}"#),
            ("users.json", r#"[{"username":"alice","platform_roles":["platform_owner","platform_observer","feature_manager","prompt_editor"]}]"#),
            ("organizations.json", r#"[{"ref":"org","name":"Org","roles":{"alice":["admin","member","member"]}}]"#),
            ("teams.json", r#"[{"ref":"team","name":"Team","organization":"org","roles":{"alice":["admin","analyst"]}}]"#),
            ("projects.json", r#"[{"ref":"project","name":"Project","team":"team","roles":{"alice":["admin"]}}]"#),
        ].into_iter().map(|(k,v)| (k.into(),v.as_bytes().to_vec())).collect()
    }
    fn pack(files: &BTreeMap<String, Vec<u8>>, method: zip::CompressionMethod) -> Vec<u8> {
        let mut writer = zip::ZipWriter::new(Cursor::new(Vec::new()));
        for (name, data) in files {
            writer
                .start_file(
                    name,
                    zip::write::SimpleFileOptions::default().compression_method(method),
                )
                .unwrap();
            writer.write_all(data).unwrap();
        }
        writer.finish().unwrap().into_inner()
    }
    #[test]
    fn explicit_hierarchy_and_roles_are_preserved() {
        for method in [
            zip::CompressionMethod::Stored,
            zip::CompressionMethod::Deflated,
        ] {
            let b = Bundle::parse(&pack(&files(), method)).unwrap();
            assert_eq!(b.users[0].platform.len(), 4);
            assert_eq!(b.spaces[0].roles["alice"], [Role::Admin, Role::Member]);
            assert_eq!(b.spaces[1].roles["alice"], [Role::Admin, Role::Analyst]);
            assert_eq!(b.spaces[2].roles["alice"], [Role::Admin]);
            assert_eq!(b.spaces[1].parent, Some(0));
            assert_eq!(b.spaces[2].parent, Some(1));
        }
    }
    #[test]
    fn space_names_share_the_creation_contract_without_folder_path_rules() {
        for file in ["organizations.json", "teams.json", "projects.json"] {
            for (name, valid) in [
                ("".to_owned(), false),
                ("  ".into(), false),
                ("a\nb".into(), false),
                ("é".repeat(181), false),
                ("é".repeat(180), true),
                (" R&D / TSN ".into(), true),
            ] {
                let mut f = files();
                let mut value: serde_json::Value = serde_json::from_slice(&f[file]).unwrap();
                value[0]["name"] = name.clone().into();
                f.insert(file.into(), serde_json::to_vec(&value).unwrap());
                let result = Bundle::parse(&pack(&f, zip::CompressionMethod::Stored));
                assert_eq!(result.is_ok(), valid, "{file}: {name:?}");
                if let Ok(bundle) = result {
                    assert!(bundle.spaces.iter().any(|space| space.name == name));
                }
            }
        }
    }
    #[test]
    fn old_and_unknown_formats_are_explicitly_unsupported() {
        assert!(matches!(
            Bundle::parse(br#" {"organization":{}}"#),
            Err(InputError::Unsupported)
        ));
        let mut f = files();
        f.insert("manifest.json".into(), include_bytes!("../../control-plane-backend/tests/fixtures/import_export/demo_provisioning/manifest.json").to_vec());
        assert!(matches!(
            Bundle::parse(&pack(&f, zip::CompressionMethod::Stored)),
            Err(InputError::Unsupported)
        ));
        for manifest in [
            r#"{"format_version":3,"users_schema_version":2,"source_platform":"swift"}"#,
            r#"{"format_version":2,"users_schema_version":3,"source_platform":"swift"}"#,
        ] {
            f.insert("manifest.json".into(), manifest.as_bytes().to_vec());
            assert!(matches!(
                Bundle::parse(&pack(&f, zip::CompressionMethod::Stored)),
                Err(InputError::Unsupported)
            ));
        }
        let mut f = files();
        f.insert("documents.json".into(), b"[]".to_vec());
        assert!(matches!(
            Bundle::parse(&pack(&f, zip::CompressionMethod::Stored)),
            Err(InputError::Unsupported)
        ));
    }
    // Proves: I11, I18
    #[test]
    fn invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input() {
        for (file, data) in [
            (
                "users.json",
                r#"[{"username":"alice","username":"private-password"}]"#,
            ),
            (
                "users.json",
                r#"[{"username":"alice"},{"username":"alice"}]"#,
            ),
            ("users.json", r#"[{"username":"Alice"}]"#),
            ("users.json", r#"[{"username":" alice"}]"#),
            ("users.json", r#"[{"username":"alice "}]"#),
            ("users.json", r#"[{"username":"al\nice"}]"#),
            ("users.json", r#"[{"username":"alice","teams":[]}]"#),
            (
                "users.json",
                r#"[{"username":"alice","platform_roles":["owner"]}]"#,
            ),
            (
                "users.json",
                r#"[{"username":"alice","platform_roles":["observer"]}]"#,
            ),
            (
                "users.json",
                r#"[{"username":"alice","platform_roles":["private-password"]}]"#,
            ),
            ("organizations.json", "[]"),
            (
                "organizations.json",
                r#"[{"ref":"org","name":"Org","roles":{"alice":["admin"],"alice":["member"]}}]"#,
            ),
            (
                "organizations.json",
                r#"[{"ref":"org","name":"Org","roles":{"absent":["admin"]}}]"#,
            ),
            (
                "organizations.json",
                r#"[{"ref":"org","name":"Org","roles":{"alice":["owner"]}}]"#,
            ),
            (
                "teams.json",
                r#"[{"ref":"team","name":"Team","organization":"absent","roles":{}}]"#,
            ),
            (
                "teams.json",
                r#"[{"ref":"org","name":"Team","organization":"org","roles":{}}]"#,
            ),
            (
                "teams.json",
                r#"[{"ref":"t1","name":"Team","organization":"org","roles":{}},{"ref":"t2","name":"Team","organization":"org","roles":{}}]"#,
            ),
            (
                "projects.json",
                r#"[{"ref":"p","name":"P","team":"org","roles":{}}]"#,
            ),
            (
                "projects.json",
                r#"[{"ref":"p","name":"P","team":"team","roles":{"alice":["private-password"]}}]"#,
            ),
            ("projects.json", "["),
        ] {
            let mut f = files();
            f.insert(file.into(), data.as_bytes().to_vec());
            let error = Bundle::parse(&pack(&f, zip::CompressionMethod::Stored))
                .err()
                .expect(file);
            assert!(matches!(error, InputError::Invalid), "{file}");
            assert!(!error.to_string().contains("private-password"));
        }
    }
    #[test]
    fn archive_boundaries_paths_duplicates_encryption_symlinks_and_crc_are_rejected() {
        let bytes = pack(&files(), zip::CompressionMethod::Deflated);
        assert!(matches!(
            Bundle::parse_limited(&bytes, bytes.len() - 1, MAX_EXPANDED),
            Err(InputError::TooLarge)
        ));
        assert!(matches!(
            Bundle::parse_limited(&bytes, bytes.len(), 10),
            Err(InputError::TooLarge)
        ));
        for missing in FILES {
            let mut f = files();
            f.remove(missing);
            assert!(Bundle::parse(&pack(&f, zip::CompressionMethod::Stored)).is_err());
        }
        for path in [
            "../users.json",
            "dir/users.json",
            "/users.json",
            r"dir\users.json",
        ] {
            let mut f = files();
            let data = f.remove("users.json").unwrap();
            f.insert(path.into(), data);
            assert!(Bundle::parse(&pack(&f, zip::CompressionMethod::Stored)).is_err());
        }
        let original = pack(&files(), zip::CompressionMethod::Stored);
        // Two existing names become identical in both local headers and the directory.
        let mut duplicate = original.clone();
        for at in (0..duplicate.len() - 10).collect::<Vec<_>>() {
            if &duplicate[at..at + 10] == b"teams.json" {
                duplicate[at..at + 10].copy_from_slice(b"users.json");
            }
        }
        assert!(matches!(
            Bundle::parse(&duplicate),
            Err(InputError::Invalid)
        ));
        for mutation in [
            "encrypted",
            "local-path",
            "local-encryption",
            "symlink",
            "crc",
            "size",
            "truncated",
        ] {
            let mut bytes = original.clone();
            let central = bytes.windows(4).position(|w| w == b"PK\x01\x02").unwrap();
            match mutation {
                "encrypted" => {
                    bytes[6] |= 1;
                    bytes[central + 8] |= 1;
                }
                "local-path" => {
                    bytes[30] = b'/';
                }
                "local-encryption" => {
                    bytes[6] |= 1;
                }
                "symlink" => {
                    bytes[central + 5] = 3;
                    bytes[central + 38..central + 42]
                        .copy_from_slice(&(0o120777u32 << 16).to_le_bytes());
                }
                "crc" => {
                    bytes[14] ^= 1;
                    bytes[central + 16] ^= 1;
                }
                "size" => {
                    bytes[22..26].fill(0);
                    bytes[central + 24..central + 28].fill(0);
                }
                _ => {
                    bytes.pop();
                }
            }
            assert!(Bundle::parse(&bytes).is_err(), "{mutation}");
        }
        assert!(Bundle::parse(b"not a zip").is_err());
    }
    #[test]
    fn real_make_target_supports_space_paths_and_replaces_previous_entries() {
        let temp = std::env::temp_dir().join(format!("manager bundle {}", uuid::Uuid::new_v4()));
        let source = temp.join("fixture directory");
        std::fs::create_dir_all(&source).unwrap();
        for name in FILES {
            std::fs::copy(
                format!("tests/fixtures/import_export/demo_provisioning/{name}"),
                source.join(name),
            )
            .unwrap();
        }
        let output = temp.join("output directory/demo.zip");
        std::fs::create_dir_all(output.parent().unwrap()).unwrap();
        std::fs::write(&output, b"old invalid content").unwrap();
        let status = std::process::Command::new("make")
            .arg("build-demo-bundle")
            .env("DEMO_PROVISIONING_FIXTURE_DIR", &source)
            .env("DEMO_BUNDLE_FILE", &output)
            .status()
            .unwrap();
        assert!(status.success());
        let bytes = std::fs::read(&output).unwrap();
        let b = Bundle::parse(&bytes).unwrap();
        assert_eq!(b.users.len(), 15);
        assert_eq!(b.spaces.len(), 4);
        let archive = zip::ZipArchive::new(Cursor::new(bytes)).unwrap();
        assert_eq!(archive.len(), 5);
        // A missing source file cannot replace a previously valid artifact.
        std::fs::remove_file(source.join("projects.json")).unwrap();
        let before = std::fs::read(&output).unwrap();
        let failed = std::process::Command::new("make")
            .arg("build-demo-bundle")
            .env("DEMO_PROVISIONING_FIXTURE_DIR", &source)
            .env("DEMO_BUNDLE_FILE", &output)
            .output()
            .unwrap();
        assert!(!failed.status.success());
        assert_eq!(before, std::fs::read(&output).unwrap());
        std::fs::remove_dir_all(temp).unwrap();
    }
}
