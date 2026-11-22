use fred_wiki::{Document, MAX_PAGE_CHARS, Page};

fn document(yaml: &str) -> String {
    format!("---\n{yaml}\n---\n# Body\n")
}

#[test]
fn absent_header_is_never_markdown_normalization() {
    for text in [
        "",
        "# Title\r\n\r\nBody  \r\n",
        " ---\nx: y\n---",
        "--- \nx: y\n---",
        "\u{feff}---\nx: y\n---",
        "---\r",
    ] {
        let page = Page::parse(text).unwrap();
        assert!(page.header().is_none(), "{text:?}");
        assert_eq!(page.body().as_bytes(), text.as_bytes());
        assert_eq!(page.edit_header(|_| Ok(())).unwrap(), text);
        page.validate_native().unwrap();
    }
}

#[test]
fn delimiters_are_exact_and_body_boundaries_preserve_lf_and_crlf() {
    for newline in ["\n", "\r\n"] {
        let body = "\r\n# Éléphant 🦀\nText  \r\n---\n\tlast";
        let text = format!("---{newline}type: topic{newline}---{newline}{body}");
        let page = Page::parse(&text).unwrap();
        assert_eq!(page.body().as_bytes(), body.as_bytes());
        assert_eq!(page.edit_header(|_| Ok(())).unwrap(), text);
        let edited = page
            .edit_header(|header| {
                header.set_path("description", "A useful page.")?;
                Ok(())
            })
            .unwrap();
        assert_eq!(
            Page::parse(&edited).unwrap().body().as_bytes(),
            body.as_bytes()
        );
        let no_body = format!("---{newline}{{}}{newline}---");
        assert_eq!(Page::parse(&no_body).unwrap().body(), "");
    }
    for text in ["---", "---\n", "---\n{}\n--- ", "---\n{}\n---\r"] {
        assert!(Page::parse(text).unwrap_err().message.contains("unclosed"));
    }
}

#[test]
fn insertion_keeps_every_original_body_byte() {
    for body in ["", "\r\n# Body\r\n", "plain\n---\ntext", "🦀\r\n  "] {
        let edited = Page::parse(body)
            .unwrap()
            .edit_header(|header| {
                header.set_path("type", "topic")?;
                Ok(())
            })
            .unwrap();
        assert_eq!(
            Page::parse(&edited).unwrap().body().as_bytes(),
            body.as_bytes()
        );
    }
}

#[test]
fn malformed_headers_and_duplicate_keys_are_errors_not_absence() {
    for yaml in [
        "type: [",
        "type: topic\ntype: source",
        "x: {a: 1, a: 2}",
        "x: &x [*x]",
        "x: *undefined",
        "x: {0123: one, 123: two}",
        "null",
        "",
        "[]",
        "text",
        "---\ntype: topic",
    ] {
        assert!(Page::parse(&document(yaml)).is_err(), "{yaml:?}");
    }
    assert!(Page::parse(&document("{}")).is_ok());
}

#[test]
fn yaml_12_scalars_and_unknown_yaml_values_survive_edits() {
    let text = document(
        "# comment\ntype: Custom Imported Type\nx: {yes: on, no: off, boolean: true, integer: 0o12}\nx-floats: [.nan, .inf, -.inf]\nx-tag: !Domain {nested: [null, 2.5, text]}\nx-key: {? [a, b]: value}\nsources:\n- resource: /page.md\n  x-extra: {nested: [true, null, 18446744073709551615]}\ngenerated: {by: 'human:a', x-extra: !Custom [1, 2]}",
    );
    let page = Page::parse(&text).unwrap();
    assert_eq!(
        page.authored().page_type.as_deref(),
        Some("Custom Imported Type")
    );
    assert_eq!(
        page.header()
            .unwrap()
            .get_path("x.yes")
            .unwrap()
            .as_str()
            .as_deref(),
        Some("on")
    );
    assert_eq!(
        page.header()
            .unwrap()
            .get_path("x.boolean")
            .unwrap()
            .as_bool(),
        Some(true)
    );
    assert_eq!(
        page.header()
            .unwrap()
            .get_path("x.integer")
            .unwrap()
            .as_i64(),
        Some(10)
    );
    assert_eq!(page.edit_header(|_| Ok(())).unwrap(), text);
    let expected = text
        .replace("/page.md", "/renamed.md")
        .replace("human:a", "human:b");
    let edited = page
        .edit_header(|header| {
            header.set_path("sources[0].resource", "/renamed.md")?;
            header.set_path("generated.by", "human:b")?;
            Ok(())
        })
        .unwrap();
    assert_eq!(edited, expected);
    let edited = Page::parse(&edited).unwrap();
    assert_eq!(edited.body(), page.body());
}

#[test]
fn yaml_core_decimal_with_leading_zero_retains_its_integer_type() {
    // YAML 1.2 Core resolves [-+]?[0-9]+ as integers, not strings.
    let text = document("x-unknown: 0123");
    let page = Page::parse(&text).unwrap();
    assert_eq!(
        page.header().unwrap().get("x-unknown").unwrap().as_u64(),
        Some(123)
    );
    let edited = page
        .edit_header(|header| {
            header.set_path("description", "An unrelated edit.")?;
            Ok(())
        })
        .unwrap();
    let edited = Page::parse(&edited).unwrap();
    assert_eq!(
        edited.header().unwrap().get("x-unknown").unwrap().as_u64(),
        Some(123)
    );
}

#[test]
fn reading_is_separate_from_native_authoring_policy() {
    let text = document(
        "type: Custom Imported Type\nverified: {by: 'human:a', at: 2026-11-22}\nstale_after: bad-date\nsources: [{title: incomplete}, {resource: /page.md}]",
    );
    let page = Page::parse(&text).unwrap();
    assert_eq!(page.authored().sources.len(), 1);
    assert_eq!(page.authored().sources[0].resource, "/page.md");
    assert_eq!(page.edit_header(|_| Ok(())).unwrap(), text);
    assert_eq!(page.validate_native().unwrap_err().path, "verified");
    let text = document("type: Custom Imported Type");
    assert_eq!(
        Page::parse(&text)
            .unwrap()
            .validate_native()
            .unwrap_err()
            .path,
        "type"
    );
}

#[test]
fn optional_fields_accept_absent_null_empty_and_singletons_without_rewriting() {
    for empty in ["null", "''", "[]"] {
        let text = document(&format!(
            "type: {empty}\ndescription: {empty}\ntags: {empty}\nsources: {empty}\nstale_after: {empty}\nx-fred-aliases: {empty}\nx-fred-read-when: {empty}"
        ));
        let page = Page::parse(&text).unwrap();
        page.validate_native().unwrap();
        let fields = page.authored();
        assert_eq!(fields.page_type, None);
        assert_eq!(fields.description, None);
        assert!(fields.tags.is_empty() && fields.sources.is_empty() && fields.aliases.is_empty());
        assert!(fields.stale_after.is_none() && fields.read_when.is_none());
        assert_eq!(page.edit_header(|_| Ok(())).unwrap(), text);
    }
    let text = document(
        "tags: 'one,two'\nsources: {resource: /page.md, x-revision: abc}\nx-fred-aliases: other",
    );
    let page = Page::parse(&text).unwrap();
    page.validate_native().unwrap();
    assert_eq!(page.authored().tags, ["one,two"]);
    assert_eq!(page.authored().aliases, ["other"]);
    assert_eq!(
        page.authored().sources[0]
            .fields
            .get("x-revision")
            .unwrap()
            .as_str()
            .as_deref(),
        Some("abc")
    );
}

#[test]
fn native_types_are_closed_but_missing_type_is_allowed() {
    for kind in [
        "topic",
        "procedure",
        "decision",
        "reference",
        "source",
        "hub",
        "untyped",
    ] {
        Page::parse(&document(&format!("type: {kind}")))
            .unwrap()
            .validate_native()
            .unwrap();
    }
    Page::parse("human page")
        .unwrap()
        .validate_native()
        .unwrap();
    Page::parse(&document("description: A human page."))
        .unwrap()
        .validate_native()
        .unwrap();
}

#[test]
fn derived_fields_are_rejected_even_when_empty_and_nested_extension_names_are_allowed() {
    for name in ["generated", "verified", "status", "superseded_by", "title"] {
        for value in ["null", "''", "[]", "{}", "forged"] {
            let error = Page::parse(&document(&format!("{name}: {value}")))
                .unwrap()
                .validate_native()
                .unwrap_err();
            assert_eq!(error.path, name);
        }
    }
    Page::parse(&document(
        "x-extra: {title: nested, verified: true}\nsources: {resource: /a.md, title: Source}",
    ))
    .unwrap()
    .validate_native()
    .unwrap();
}

#[test]
fn native_validation_identifies_field_paths() {
    for (yaml, path) in [
        ("type: true", "type"),
        ("description: {}", "description"),
        ("tags: [tag, 42]", "tags[1]"),
        ("x-fred-aliases: false", "x-fred-aliases[0]"),
        ("x-fred-read-when: {}", "x-fred-read-when"),
        ("sources: [true]", "sources[0]"),
        ("sources: [{resource: /a}, {}]", "sources[1].resource"),
        ("sources: {resource: /a, title: true}", "sources[0].title"),
        (
            "sources: {resource: /a, last_modified: nonsense}",
            "sources[0].last_modified",
        ),
        ("stale_after: tomorrow", "stale_after"),
    ] {
        assert_eq!(
            Page::parse(&document(yaml))
                .unwrap()
                .validate_native()
                .unwrap_err()
                .path,
            path
        );
    }
}

#[test]
fn description_uses_unicode_scalars_and_one_line_not_sentence_detection() {
    for description in [
        "🦀".repeat(300),
        "e\u{301}".repeat(150),
        "First sentence. Second sentence.".into(),
    ] {
        let text = document(&format!("description: {description}"));
        Page::parse(&text).unwrap().validate_native().unwrap();
    }
    for description in [
        "🦀".repeat(301),
        "e\u{301}".repeat(151),
        "first\nsecond".into(),
        "first\rsecond".into(),
        "first\u{85}second".into(),
        "first\u{2028}second".into(),
        "first\u{2029}second".into(),
    ] {
        let mut header = Document::parse("{}\n").unwrap();
        header.set_path("description", description).unwrap();
        let text = document(&header.to_string());
        assert_eq!(
            Page::parse(&text)
                .unwrap()
                .validate_native()
                .unwrap_err()
                .path,
            "description"
        );
    }
}

#[test]
fn page_ceiling_and_nul_are_checked_before_parse_and_after_edits() {
    assert!(Page::parse(&"🦀".repeat(MAX_PAGE_CHARS)).is_ok());
    assert!(Page::parse(&"🦀".repeat(MAX_PAGE_CHARS + 1)).is_err());
    for text in ["body\0", "---\ntype: topic\n---\n\0"] {
        assert!(Page::parse(text).is_err());
    }
    let oversized = format!("---\n[{}", "x".repeat(MAX_PAGE_CHARS));
    assert!(
        Page::parse(&oversized)
            .unwrap_err()
            .message
            .contains("exceeds")
    );
    let body = "x".repeat(MAX_PAGE_CHARS);
    assert!(
        Page::parse(&body)
            .unwrap()
            .edit_header(|map| {
                map.set_path("type", "topic")?;
                Ok(())
            })
            .is_err()
    );
    assert!(
        Page::parse("")
            .unwrap()
            .edit_header(|map| {
                map.set_path("x", "x".repeat(MAX_PAGE_CHARS))?;
                Ok(())
            })
            .is_err()
    );
}

#[test]
fn retained_yaml_guards_reject_excessive_nesting_and_alias_materialization() {
    let moderate = format!("x: {}0{}", "[".repeat(20), "]".repeat(20));
    assert!(Page::parse(&document(&moderate)).is_ok());
    let excessive = format!("x: {}0{}", "[".repeat(140), "]".repeat(140));
    let error = Page::parse(&document(&excessive)).unwrap_err();
    assert!(error.message.contains("nested too deeply"), "{error}");
    let harmless = document("x: &x {a: [1, 2]}\ny: *x");
    assert!(Page::parse(&harmless).is_ok());
    let mut aliases = "a: &a [0]\n".to_owned();
    for (current, previous) in [
        ('b', 'a'),
        ('c', 'b'),
        ('d', 'c'),
        ('e', 'd'),
        ('f', 'e'),
        ('g', 'f'),
        ('h', 'g'),
        ('i', 'h'),
    ] {
        aliases.push_str(&format!(
            "{current}: &{current} [{}]\n",
            vec![format!("*{previous}"); 10].join(", ")
        ));
    }
    let error = Page::parse(&document(&aliases)).unwrap_err();
    assert!(error.message.contains("aliases expand"), "{error}");
    // Few nodes can still amplify an escaped scalar beyond the byte budget.
    let aliases = format!(
        "x: &x \"{}\"\ntags: [{}]",
        "\\n".repeat(5000),
        vec!["*x"; 2000].join(",")
    );
    let error = Page::parse(&document(&aliases)).unwrap_err();
    assert!(error.message.contains("materialises more than"), "{error}");
}

#[test]
fn editing_is_format_only_native_policy_remains_explicit() {
    let result = Page::parse("body")
        .unwrap()
        .edit_header(|header| {
            header.set_path("title", "forged")?;
            Ok(())
        })
        .unwrap();
    assert_eq!(
        Page::parse(&result)
            .unwrap()
            .validate_native()
            .unwrap_err()
            .path,
        "title"
    );
    let result = Page::parse("body")
        .unwrap()
        .edit_header(|header| {
            header.set_path("x", vec![Option::<u8>::None])?;
            Ok(())
        })
        .unwrap();
    Page::parse(&result).unwrap().validate_native().unwrap();
}

#[test]
fn unknown_numeric_precision_tags_and_complex_keys_remain_verbatim() {
    let unknown = "x-int: 34028236692093846346337460743176821145678901234567890\nx-float: 1.23456789012345678901234567890\nx-overflow: 1e400\nx-underflow: 1e-400\nx-nested: !Domain {tag: !Custom [null, 0.12345678901234567890]}\nx-set: !!set {key: null}\nx-key: {? [a, b]: {number: 0123}}\n";
    for newline in ["\n", "\r\n"] {
        let body = "\r\n# 🦀\nBody  \r\n";
        let yaml = format!("description: Before.\n{unknown}").replace('\n', newline);
        let content = format!("---{newline}{yaml}---{newline}{body}");
        let page = Page::parse(&content).unwrap();
        let edited = page
            .edit_header(|header| {
                header.set_path("description", "After.")?;
                Ok(())
            })
            .unwrap();
        assert_eq!(edited, content.replacen("Before.", "After.", 1));
        assert_eq!(
            Page::parse(&edited).unwrap().body().as_bytes(),
            body.as_bytes()
        );
    }
}

#[test]
fn aliases_are_read_as_scalars_lists_and_source_mappings_without_expansion() {
    let text = document(
        "x-kind: &kind topic\ntype: *kind\nx-description: &d 'A page.'\ndescription: *d\nx-tags: &tags [one, two]\ntags: *tags\nx-resource: &r /page.md\nx-source: &source {resource: *r, x-unknown: {nested: true}}\nsources: [*source]\nx-deadline: &deadline 2026-11-22\nstale_after: *deadline",
    );
    let page = Page::parse(&text).unwrap();
    page.validate_native().unwrap();
    let authored = page.authored();
    assert_eq!(authored.page_type.as_deref(), Some("topic"));
    assert_eq!(authored.description.as_deref(), Some("A page."));
    assert_eq!(authored.tags, ["one", "two"]);
    assert_eq!(authored.sources[0].resource, "/page.md");
    assert_eq!(
        authored.sources[0]
            .fields
            .get("x-unknown")
            .unwrap()
            .get("nested")
            .unwrap()
            .as_bool(),
        Some(true)
    );
    let now = chrono::DateTime::parse_from_rfc3339("2026-11-22T00:00:00Z").unwrap();
    assert_eq!(
        fred_wiki::freshness(authored.stale_after, now),
        fred_wiki::Freshness::Stale
    );
    let edited = page
        .edit_header(|header| {
            header.set_path("description", "Changed.")?;
            Ok(())
        })
        .unwrap();
    assert_eq!(
        edited,
        text.replace("description: *d", "description: Changed.")
    );
}

#[test]
fn edits_cannot_change_values_shared_by_unknown_aliases() {
    for (yaml, path) in [
        ("description: &d Before.\nx-unknown: *d", "description"),
        (
            "sources: &s [{resource: /old}]\nx-unknown: *s",
            "sources[0].resource",
        ),
        ("x: {nested: &d Before.}\ndescription: *d", "x.nested"),
    ] {
        let text = document(yaml);
        let page = Page::parse(&text).unwrap();
        let error = page
            .edit_header(|header| {
                header.set_path(path, "Changed.")?;
                Ok(())
            })
            .unwrap_err();
        assert!(error.message.contains("anchor referenced"), "{error}");
        assert_eq!(page.edit_header(|_| Ok(())).unwrap(), text);
        // An unrelated edit remains possible even with referenced anchors.
        page.edit_header(|header| {
            header.set_path("x-independent", true)?;
            Ok(())
        })
        .unwrap();
    }
}

#[test]
fn edits_are_rechecked_for_mapping_shape_and_frontmatter_boundaries() {
    let page = Page::parse("body\r\n").unwrap();
    assert!(
        page.edit_header(|header| {
            header.set_root("not a mapping")?;
            Ok(())
        })
        .is_err()
    );
    assert!(
        page.edit_header(|header| {
            *header = Document::parse("---\ntype: topic\n").unwrap();
            Ok(())
        })
        .is_err()
    );
    let edited = page
        .edit_header(|header| {
            *header = Document::parse("{type: topic}").unwrap();
            Ok(())
        })
        .unwrap();
    assert_eq!(Page::parse(&edited).unwrap().body(), page.body());
}
