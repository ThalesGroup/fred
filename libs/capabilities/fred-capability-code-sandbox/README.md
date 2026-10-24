# Fred code sandbox capability

This admin-gated capability adds `execute_code(language, code)` to Fred agents.
Execution requires the optional `RuntimeServices.sandbox_execution` port and a separately deployed broker. The tool cannot select an isolation runtime or access broker credentials.
