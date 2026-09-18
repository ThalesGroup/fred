# Verification

- Tabular service and controller status-code suites: **54 passed, 1 integration test deselected, 3 dependency deprecation warnings** (2026-09-18).
- Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:../../libs/fred-core:../../libs/fred-sdk:../../libs/fred-runtime <existing-kf-venv>/bin/python -m pytest tests/services/test_tabular_service.py tests/features/tabular/test_tabular_controller_status_codes.py -m 'not integration' --disable-socket --allow-unix-socket -vv -o faulthandler_timeout=60`, from the isolated Knowledge Flow checkout. Existing interpreter used read-only; explicit paths select extracted source. Sandbox runs stalled in asyncio executor wakeups; the offline socket-blocked run outside the sandbox passed in 12.80 seconds.
- Changed Python files: Ruff check and formatting passed; `git diff --check` passed.
- `openspec validate explain-tabular-access-denials --strict`: passed.
- Root `make code-quality`: running with isolated dependency installations; not yet a pass.
- Independent standards/spec and performance review: pending. Keep this change active until those checks finish.
- No public schema changed; API client regeneration is unnecessary. No full backend suite or live LLM recovery campaign has been run.
