# Fred code sandbox capability

This admin-gated capability adds `execute_code(language, code)` to Fred agents.
Execution requires the optional `RuntimeServices.sandbox_execution` port and a separately deployed broker. The tool cannot select an isolation runtime or access broker credentials.

The tool description guides agents to write selective Bash or Python code. It starts with a narrow filename glob, uses literal matching for plain terms or escaped regular expressions for spelling variants, and caps text excerpts by both match count and character length. For PDF, DOCX, PPTX, CSV and XLSX, it iterates the relevant pages, rows or columns and prints only the requested excerpts or aggregates. The code remains visible in the tool detail; the chat answer should summarize the finding. These are model instructions, while broker resource and output limits remain the enforcement boundary.
