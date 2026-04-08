# Claude Instructions — claude_jobhunt

- Read global instructions at `~/CLAUDE.md` before any session
- Claude model: Sonnet 4.6 — do not use Opus
- Project directory: `~/Documents/claude_jobhunt`

## What this project is

A local daily job ingest pipeline:
- **Cowork scheduled task** reads Gmail job alerts, extracts listings, writes `/tmp/new_jobs.json`
- **process_jobs.py** ingests that file into `job_search.db` (SQLite)
- **generate_dashboard.py** rebuilds `job_dashboard.html` from the DB
- **eval_server.py** runs locally to persist dashboard evaluation choices to `job_evaluations.json`

Full workflow documentation: `COWORK_TASK.md`

## Key files

| File | Purpose |
|------|---------|
| `process_jobs.py` | Ingest worker — reads `/tmp/new_jobs.json`, upserts to DB |
| `generate_dashboard.py` | Dashboard generator — reads DB + evaluations, writes HTML |
| `eval_server.py` | Local HTTP server on port 7432 for saving evaluations |
| `rebuild_db.py` | Recovery utility — restores DB from `db_dump.sql` |
| `job_search.db` | SQLite database (personal data, not in git) |
| `job_evaluations.json` | Persisted interest/status per job (not in git) |
| `COWORK_TASK.md` | Full Cowork task instructions — preserve carefully |

## Secrets and MCP configuration

API keys are **never stored in `claude_desktop_config.json`**. They live in `~/.claude-secrets` (chmod 600) and are loaded at runtime by wrapper scripts in `~/.config/Claude/wrappers/`.

- `~/.claude-secrets` — contains `export GITHUB_PERSONAL_ACCESS_TOKEN=...` and `export BRAVE_API_KEY=...`
- `~/.config/Claude/wrappers/github-mcp.sh` — sources secrets, execs github-mcp-server via podman
- `~/.config/Claude/wrappers/brave-search-mcp.sh` — sources secrets, execs brave-search MCP via npx

If Claude Desktop loses access to GitHub or Brave Search MCP tools, check:
1. `~/.claude-secrets` exists and has `chmod 600`
2. Wrapper scripts are executable (`chmod +x`)
3. Claude Desktop has been restarted after any config change

## Important operational notes

- After a Cowork task run, **start a new chat session** before using filesystem MCP tools. Cowork overrides the filesystem MCP allowed directory to its session sandbox, which breaks filesystem access in the same conversation.
- `/tmp/new_jobs.json` is a temporary handoff file — it is overwritten each run.
- `job_evaluations.json` is independent of the database. Preserve it across any DB rebuilds.
- To back up the database: `sqlite3 job_search.db .dump > db_dump.sql`

## Running scripts manually

```bash
python3 ~/Documents/claude_jobhunt/process_jobs.py
python3 ~/Documents/claude_jobhunt/generate_dashboard.py
python3 ~/Documents/claude_jobhunt/eval_server.py
python3 ~/Documents/claude_jobhunt/rebuild_db.py
```

## No external Python dependencies

All scripts use stdlib only: `sqlite3`, `json`, `os`, `glob`, `http.server`, `datetime`.
