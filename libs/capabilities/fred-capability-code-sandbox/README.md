# Fred code sandbox capability

This admin-gated capability adds `execute_code(language, code)` and bounded `search_files(scope, file_glob, query)` to Fred agents.
Execution requires the optional `RuntimeServices.sandbox_execution` port and a separately deployed broker. The tool cannot select an isolation runtime or access broker credentials.

`search_files` runs through the same conversation sandbox lease. It lists up to 50 paths or returns up to 20 short text matches from `/inputs` or `/skills`, examining at most 1,000 matching files, 10,000 directory entries and 32 MiB. It skips symlinks and binary formats. Use `execute_code` for selective PDF, office and tabular analysis; user-facing answers should summarize findings without echoing source code or package versions.
