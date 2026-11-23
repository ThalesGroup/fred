## 1. Runtime tool access

- [x] 1.1 Expose the existing geo tool once in ReAct and Deep without a tool invoker; verify the targeted resolver test, including an explicit declaration.
- [x] 1.2 Allow Graph nodes to invoke the same built-in without a declaration and carry its UI part into the final event; verify the targeted Graph runtime tests.

## 2. Chat rendering

- [x] 2.1 Mount an interactive map for typed `GeoPart` data with a bundled offline country basemap, safe popup text, and attribution; verify the frontend renderer test and TypeScript check.
- [x] 2.2 Invoke the shared tool in the no-LLM test assistant's `geo` scenario and emit a final `GeoPart` in its `markdown` scenario; verify the targeted agent and frontend fold tests.

## 3. Review and validation

- [x] 3.1 Run touched-project quality and offline tests, then validate this OpenSpec change. All quality checks, targeted Python tests, and the full frontend suite pass. Full Python suites time out in existing tests in this workspace.
- [x] 3.2 Review the full diff against `b44254b77` and reconcile the spec and implementation. Independent review findings on Graph final parts, invoker independence, the Markdown scenario, map fallback, and offline basemap are fixed.
