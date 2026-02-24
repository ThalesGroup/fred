# Web + GitHub Read-only MCP Server

Read-only MCP server for demo/generalist agents that need minimal grounding from:
- public web pages (`web_fetch_url`)
- public GitHub repositories (`github_*`)

Transport
- Streamable HTTP at `/mcp`

Run
```bash
uvicorn web_github_readonly_mcp_server.server_mcp:app --host 127.0.0.1 --port 9799 --reload
```

Or:
```bash
make server
```

Optional environment variables
- `GITHUB_TOKEN`: optional GitHub token to increase API rate limits

Implemented tools
- `web_fetch_url(url, max_chars)`
- `github_get_repo_metadata(repo_or_url)`
- `github_read_readme(repo_or_url, ref, max_chars)`
- `github_get_repo_tree(repo_or_url, ref, max_entries)`
- `github_read_file(repo_or_url, path, ref, max_chars)`

Examples
```text
github_get_repo_metadata("ThalesGroup/fred")
github_read_readme("https://github.com/ThalesGroup/fred")
github_get_repo_tree("ThalesGroup/fred", max_entries=200)
github_read_file("ThalesGroup/fred", "README.md")
web_fetch_url("https://github.com/ThalesGroup/fred")
```

