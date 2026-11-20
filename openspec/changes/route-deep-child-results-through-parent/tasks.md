## 1. Parent-owned deliverables

- [ ] 1.1 Add the default-enabled Deep child availability declaration and build the child capability subset in the existing assembly pass; verify a focused assembly test calls each selected `tools(ctx)` once and excludes opted-out tools, middleware and HITL only from the child.
- [ ] 1.2 Opt the current HTML artifact, writable document and PowerPoint file-producing capabilities out of child execution; verify the parent still receives their tools and a child cannot invoke one by name. Apply the same declaration to the spreadsheet capability when its pending branch is integrated.
- [ ] 1.3 Give the native child its filtered tools, available-tool names and prompt; verify a focused Deep test shows no parent-only tool in the child prompt or graph while the parent can create a file card from returned working data.

## 2. Private child evidence

- [ ] 2.1 Enable namespaced updates for Deep turns with and without platform skills, and collect only child `ToolMessage.artifact` sources and non-deliverable UI parts; verify focused stream tests preserve root events and do not emit child text, reasoning, tool calls or failure state.
- [ ] 2.2 Verify with several children and a resumed HITL turn that the parent final event and saved history contain distinct child sources and parts once, with no child-authored file card or replayed tool event; include a bounded fan-out check for artifact merge cost.

## 3. Integration and close-out

- [ ] 3.1 Update the compact runtime execution contract and capability-author guidance for parent-only deliverables; verify the documented rule matches the implemented child tool and prompt behavior.
- [ ] 3.2 Refresh `graphify-out/graph.json` from the changed source and query a changed symbol; verify the generated graph is staged with the source changes.
- [ ] 3.3 Run the root quality gate once and review the full branch against its actual target with the audit procedure and independent read-only review; verify findings and any limitations are recorded in the draft PR.
- [ ] 3.4 Reconcile the change artifacts with the reviewed implementation, then sync and archive the delta spec; verify no active change remains for this outcome.
