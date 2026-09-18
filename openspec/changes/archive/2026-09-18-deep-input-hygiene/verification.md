# Verification

Prepared extraction of issues #2740 and #2741 on the provider-retry layer.

- Focused offline runtime suite: 48 passed (`make -C libs/fred-runtime test PYTEST_OPTS="tests/test_deep_agent_middleware.py tests/test_tool_loop_trim.py tests/test_react_loop_regressions_1972.py -q"`).
- A real compiled Deep parent verifies OpenAI-compatible Mistral message serialization omits assistant names, reasoning is text, tool IDs are paired, and original checkpoint messages remain intact. Deep's existing PatchToolCallsMiddleware repairs interrupted calls before Fred's wrapper; direct wrapper coverage separately proves dangling-call removal.
- Shared sanitizer tests preserve original content, IDs, names and unnamed object identity. Deep count-limit and character-limit tests cover the explicit policy split.
- Full official offline runtime suite: 1,258 passed, 16 deselected, 18 warnings (`make -C libs/fred-runtime test PYTEST_OPTS=-q`), including existing ReAct and parent HITL tests. Runtime warning classes are existing deprecations/socket-denial probes; there were no failures.
- Raw runtime `basedpyright`: 0 errors, 4 existing unreachable-code warnings (`__main__.py:80`, `common/mcp_runtime.py:290`, `test_conversational_memory.py:163,207`). No baseline changed.
- Independent standards review: one P3 stale issue reference on a rewritten test docstring, removed in follow-up `0ee250cc5`; coordinator verified resolution. Independent spec and static performance reviews: no findings. No production code changed after review.
- Full monorepo-root `make code-quality` passed all modules (including frontend TypeScript, Prettier and ESLint). Strict OpenSpec validation passed. The completed change is synchronized into `model-input-hygiene` and archived.

The approved handoff supplies implementation authorization; planning artifacts were written before implementation. No new architecture or public API is introduced. Native-child composition and native second-call verification remain in the next stack layer, so neither issue is closed by this parent-only slice. No live provider call or load campaign is claimed.
