# claude_jobhunt

A local AI-powered job search pipeline that ingests job alert emails daily, stores listings in a SQLite database, and generates an interactive HTML dashboard for reviewing and tracking applications.

## What it does

Each day, a Claude Desktop "Cowork" scheduled task:
1. Checks Gmail for new job alert emails (LinkedIn, Indeed, BioSpace, LifeSciWA, PostJobFree)
2. Extracts structured job listing data from each email
3. Writes the data to `/tmp/new_jobs.json`
4. Runs `process_jobs.py` to ingest into the database (scoring, deduplication, tagging)
5. Runs `generate_dashboard.py` to rebuild the HTML dashboard

You then open `job_dashboard.html` in a browser to review listings, mark interest, and track applications. Evaluation state is saved back to `job_evaluations.json` via `eval_server.py`.

## System requirements

- Linux (developed on Linux Mint 22.3) or macOS
- Python 3.10+
- Claude Desktop with local MCP servers:
  - `filesystem` — read/write access to project directory
  - `gmail` — Gmail MCP for reading job alert emails
  - `github` — GitHub MCP (uses wrapper script, see Secrets Management below)
  - `brave-search` — Brave Search MCP (uses wrapper script, see Secrets Management below)
- No additional Python packages required (uses stdlib only: `sqlite3`, `json`, `http.server`)

## Project structure

```
claude_jobhunt/
├── README.md                  # this file
├── CLAUDE.md                  # Claude session instructions
├── COWORK_TASK.md             # Cowork scheduled task — full instructions
├── .gitignore
├── process_jobs.py            # ingest worker: /tmp/new_jobs.json → job_search.db
├── generate_dashboard.py      # builds job_dashboard.html from DB
├── eval_server.py             # local HTTP server for saving evaluations
├── rebuild_db.py              # restore DB from db_dump.sql (recovery utility)
│
│   -- runtime files (not in git) --
├── job_search.db              # SQLite database (your personal job data)
├── db_dump.sql                # SQL dump for backup/restore
├── job_evaluations.json       # your interest/status choices per job
└── job_dashboard.html         # generated dashboard (rebuilt each run)
```

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/oldgranola/claude_jobhunt_public.git ~/Documents/claude_jobhunt
```

### 2. Configure scoring for your field and location

Open `process_jobs.py` and find the `# ── USER CONFIGURATION ──` block near the top. Edit:

- **`BIO_NAMES`** — exact or partial company names you want to prioritize (+20 pts each match)
- **`BIO_KW`** — keywords in company names that indicate your target sector (+20 pts)
- **`HUBS`** — city or region keywords for locations you prefer (+15 pts)
- The discipline keyword lists (`BIOINFO`, `ML`, `DRUGDISC`, etc.) if your field differs

The defaults are configured for **biotech/life-sciences** as a worked example. The scoring logic is in the `score()` function just below the configuration block.

### 3. Set up secrets (required before Claude Desktop will work)

API keys and tokens are **never stored in config files**. They live in `~/.claude-secrets`, a permission-restricted plain text file outside any git repo, sourced at runtime by wrapper scripts.

```bash
touch ~/.claude-secrets && chmod 600 ~/.claude-secrets
```

Open it and add your keys:

```bash
# ~/.claude-secrets — never commit, never share
export GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token_here
export BRAVE_API_KEY=your_brave_key_here
```

Then make the MCP wrapper scripts executable:

```bash
chmod +x ~/.config/Claude/wrappers/github-mcp.sh
chmod +x ~/.config/Claude/wrappers/brave-search-mcp.sh
```

### 4. Set up Claude Desktop MCP servers

See the [claude-desktop-mcp-setup](https://github.com/oldgranola/claude-desktop-mcp-setup) repo for a full setup guide.

Ensure your `~/.config/Claude/claude_desktop_config.json` has:
- `filesystem` MCP pointed at your home directory
- `gmail` MCP connected
- `github` entry pointing to `~/.config/Claude/wrappers/github-mcp.sh`
- `brave-search` entry pointing to `~/.config/Claude/wrappers/brave-search-mcp.sh`

### 5. Create the Cowork scheduled task

See `COWORK_TASK.md` for the exact task instructions to paste into Claude Desktop's Cowork scheduler.

### 6. Start the evaluation server (optional, for saving status choices)

Run this once before opening the dashboard, and keep it running while you use it:

```bash
python3 ~/Documents/claude_jobhunt/eval_server.py
```

The dashboard will show "Server connected ✓" when it is running. Without it, your evaluations are saved to browser localStorage only and will be lost if the dashboard is regenerated.

## Secrets management

API keys and tokens are kept out of all config files and git history:

- `~/.claude-secrets` — single plain text file, `chmod 600`, outside every git repo.
- `~/.config/Claude/wrappers/` — shell scripts that `source ~/.claude-secrets` and then exec the real MCP server.

**Never:**
- Put tokens directly in `claude_desktop_config.json`
- Commit `~/.claude-secrets` to any repo

## Daily workflow

The Cowork task runs automatically on schedule. After it completes:

1. Open `job_dashboard.html` in your browser
2. Review new listings (sorted by match score)
3. Mark each as: **Interested / Viewed / Hidden / Applied**
4. Click **Save Evaluations** to persist to `job_evaluations.json`

## Match scoring

Jobs are scored 0–100. Defaults are tuned for biotech/life-sciences as a worked example.
Edit the `USER CONFIGURATION` block in `process_jobs.py` to fit your own field.

| Signal | Points |
|--------|--------|
| Known target company name (BIO_NAMES) | +20 |
| Target sector keyword in company name (BIO_KW) | +20 |
| Bioinformatics/genomics keywords in title | +20 |
| ML/data science keywords in title | +15 |
| Drug discovery/wet lab keywords in title | +15 |
| Salary ≥ $150K | +10 |
| Preferred location (HUBS) | +15 |
| Clinical research keywords | +10 |
| Senior/director/lead title | +10 |

## Database schema

Main tables: `jobs`, `companies`, `email_log`, `run_log`, `applications`, `tags`, `job_tags`, `job_company_link`, `search_criteria`.

Schema is defined and auto-applied in `process_jobs.py` (SCHEMA constant).

## Backup and recovery

```bash
sqlite3 ~/Documents/claude_jobhunt/job_search.db .dump > ~/Documents/claude_jobhunt/db_dump.sql
python3 ~/Documents/claude_jobhunt/rebuild_db.py
```

## Notes

- After running a Cowork task, start a **new Chat session** before using filesystem MCP tools.
- `job_evaluations.json` must be preserved across DB rebuilds — it is independent of the database.
- The `/tmp/new_jobs.json` file is a temporary handoff between the Cowork task and `process_jobs.py`.
