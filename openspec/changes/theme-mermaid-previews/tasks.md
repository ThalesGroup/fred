## 1. Rendering integration

- [ ] 1.1 Add beautiful-mermaid and declare directly imported sanitization dependencies in the frontend manifests; verify reproducible installation and on-demand imports in the Vite production build.
- [ ] 1.2 Add a co-located rendering adapter and replace MermaidBlock's normal rendering path, retaining raw-first compatibility and the existing repair fallback; verify actual preferred-renderer fixtures for six diagram families and compatibility tests for semicolon headers, pie/Gantt, repaired labels and invalid input.
- [ ] 1.3 Isolate SVG styles and view-specific IDs/references, remove external font imports and sanitize untrusted output; verify safe labels, preserved geometry and simultaneous inline/enlarged diagrams in browser-faithful DOM tests.

## 2. Theme coherence and existing interactions

- [ ] 2.1 Bind diagram colors/font to the existing Fred tokens and refresh compatibility renders when theme or mode changes; verify token mapping and mounted-preview updates without library palette presets.
- [ ] 2.2 Preserve source copy, FullPageModal enlargement, errors, cancellation and completed-fence streaming behavior; verify component tests and the affected Markdown/clipboard regression suites.
- [ ] 2.3 Validate representative diagrams on existing Markdown surfaces in Pebble, Cobalt and Cloud, both modes, a deployment token override and a narrow viewport; record observable results and any unverified cases in this task file or the PR.

## 3. Verification and delivery

- [ ] 3.1 Update the existing COMPONENT-UX.md rendering entry and add an English impact-none migration note; verify both describe the resulting behavior and run the migration-note check.
- [ ] 3.2 Run the frontend default tests, production build and root make code-quality after the related changes; record exact outcomes and attributable pre-existing failures.
- [ ] 3.3 Apply audit-branch against the actual swift base and obtain an independent read-only review of the complete implementation; record reviewed base/head, consumer coverage, findings/dispositions and exclusions in the PR.
- [ ] 3.4 Reconcile this change with verification, sync/archive it once all tasks are complete, commit reviewable blocks, then push and open a draft PR linked to #3252; verify strict OpenSpec validation and a clean scoped diff before delivery.
