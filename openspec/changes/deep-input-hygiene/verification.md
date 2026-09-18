# Verification

Prepared extraction of issues #2740 and #2741 on the provider-retry layer.

- Focused offline runtime suite: 48 passed (`make -C libs/fred-runtime test PYTEST_OPTS="tests/test_deep_agent_middleware.py tests/test_tool_loop_trim.py tests/test_react_loop_regressions_1972.py -q"`).
- A real compiled Deep parent verifies OpenAI-compatible Mistral message serialization omits assistant names, reasoning is text, tool IDs are paired, and original checkpoint messages remain intact. Deep's existing PatchToolCallsMiddleware repairs interrupted calls before Fred's wrapper; direct wrapper coverage separately proves dangling-call removal.
- Shared sanitizer tests preserve original content, IDs, names and unnamed object identity. Deep count-limit and character-limit tests cover the explicit policy split.
- Strict OpenSpec validation passed. Root quality, full runtime suite and independent reviews remain in progress.

The approved handoff supplies implementation authorization; planning artifacts were written before implementation. No new architecture or public API is introduced. Native-child composition and native second-call verification remain in the next stack layer, so neither issue is closed by this parent-only slice. No live provider call or load campaign is claimed.
