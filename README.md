# claude_jobhunt

A local AI-powered job search pipeline that ingests job alert emails daily, stores listings in a SQLite database, and generates an interactive HTML dashboard for reviewing and tracking applications.

This is the public, generalized version. The scoring constants in `process_jobs.py` use generic biotech/life-sciences examples — replace them with companies and locations relevant to your own job search.

## What it does

Each day, a Claude Desktop "Cowork" scheduled task:
1. Checks Gmail for new job alert emails (LinkedIn, Indeed, BioSpace, LifeSciWA, PostJobFree)
2. Extracts structured job listing data from each email using Claude as the extraction engine
3. Writes the extracted data to `/tmp/new_jobs.json` via a generated `build_jobs.py` script
4. Runs `process_jobs.py` to ingest into the database (scoring, deduplication, tagging)
5. Runs `generate_dashboard.py` to rebuild the HTML dashboard

You then open `job_dashboard.html` in a browser to review listings, mark interest, and track applications. Evaluation state is saved back to `job_evaluations.json` via `eval_server.py`.

## System requirements

- Linux (developed on Linux Mint 22.3) or macOS
- Python 3.10+
- Claude Desktop with local MCP servers:
  - `filesystem` — read/write access to project directory
  - `gmail-raw` — custom Gmail MCP for reading job alert emails with correct URL decoding (see note below)
  - `github` — GitHub MCP (uses wrapper script, see Secrets Management below)
  - `brave-search` — Brave Search MCP (uses wrapper script, see Secrets Management below)
- No additional Python packages required (uses stdlib only: `sqlite3`, `json`, `http.server`, `quopri`)

### Why gmail-raw instead of the standard Google Gmail MCP

The standard Google Gmail MCP uses `format=full`, which pre-decodes quoted-printable content server-side. This corrupts URLs in Indeed job alert emails: sequences like `=d5` are interpreted as QP-escaped bytes, truncating the `jk=` job ID parameter (e.g. `d58b5cd1ea1ee67b` becomes `8b5cd1ea1ee67b`), producing broken job links.

The `gmail-raw` MCP uses `format=raw`, returning the untouched RFC 2822 message, then applies Python's `quopri` module for correct decoding. All href values are intact. See `COWORK_TASK.md` for details on setting up the gmail-raw MCP.

## Project structure

```
claude_jobhunt/
├── README.md                  # this file
├── CLAUDE.md                  # Claude session instructions
├── COWORK_TASK.md             # Cowork scheduled task — full instructions
├── .gitignore
├── process_jobs.py            # ingest worker: /tmp/new_jobs.json -> job_search.db
├── generate_dashboard.py      # builds job_dashboard.html from DB
├── eval_server.py             # local HTTP server for saving evaluations and presets
├── rebuild_db.py              # restore DB from db_dump.sql (recovery utility)
├── check_dupes.py             # utility: inspect duplicate/near-duplicate jobs in DB
├── cleanup_old_jobs.py        # utility: mark old inactive jobs as closed
├── build_jobs.example.py      # example of the Claude-generated extraction output
│
│   -- runtime files (not in git) --
├── build_jobs.py              # Claude-generated each run, excluded from git
├── job_search.db              # SQLite database (your personal job data)
├── db_dump.sql                # SQL dump for backup/restore
├── job_evaluations.json       # your interest/status choices per job
├── job_presets.json           # saved dashboard filter presets
└── job_dashboard.html         # generated dashboard (rebuilt each run)
```

### About build_jobs.py

`build_jobs.py` is not a file you write or maintain. Claude generates it fresh during each Cowork task run, populated with the job data extracted from that run's emails. It is executed immediately by the pipeline to produce `/tmp/new_jobs.json`, then its job is done. It is excluded from git because it contains the live output of a specific run, not reusable code. See `build_jobs.example.py` for a documented example of the structure.

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/oldgranola/claude_jobhunt_public.git ~/Documents/claude_jobhunt
```

### 2. Customize scoring for your job search

Open `process_jobs.py` and find the `USER CONFIGURATION` block near the top. Replace the example company names and location hubs with ones relevant to your field and geography. This is the primary thing you need to personalize.

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

The wrapper scripts themselves live at `~/.config/Claude/wrappers/` — see that directory's `README.md` for full details. They are not in this repo because they are part of the Claude Desktop configuration, not the project.

### 4. Set up the gmail-raw MCP

The gmail-raw MCP is a separate server that must be installed and configured. See `COWORK_TASK.md` for the full setup instructions, including the auth flow and token path.

### 5. Set up Claude Desktop MCP servers

Ensure your `~/.config/Claude/claude_desktop_config.json` has:
- `filesystem` MCP pointed at your home directory
- `gmail-raw` MCP connected and authenticated
- `github` entry pointing to `~/.config/Claude/wrappers/github-mcp.sh`
- `brave-search` entry pointing to `~/.config/Claude/wrappers/brave-search-mcp.sh`

The GitHub and Brave entries should look like this — no tokens in the file:

```json
"github": {
  "command": "/home/YOUR_USER/.config/Claude/wrappers/github-mcp.sh",
  "args": []
},
"brave-search": {
  "command": "/home/YOUR_USER/.config/Claude/wrappers/brave-search-mcp.sh",
  "args": []
}
```

### 6. Create the Cowork scheduled task

See `COWORK_TASK.md` for the exact task instructions to paste into Claude Desktop's Cowork scheduler.

### 7. Initialise the database

The database is created automatically on first run of `process_jobs.py`. To create it manually:

```bash
python3 -c "import sqlite3; conn = sqlite3.connect('~/Documents/claude_jobhunt/job_search.db'); conn.close()"
```

### 8. Start the evaluation server (optional, for saving status choices)

Run this once before opening the dashboard, and keep it running while you use it:

```bash
python3 ~/Documents/claude_jobhunt/eval_server.py
```

The dashboard will show "Server connected ✓" when it is running. Without it, your evaluations are saved to browser localStorage only and will be lost if the dashboard is regenerated.

## Secrets management

API keys and tokens are kept out of all config files and git history using this pattern:

- `~/.claude-secrets` — single plain text file, `chmod 600`, outside every git repo. Contains `export KEY=value` lines.
- `~/.config/Claude/wrappers/` — shell scripts that `source ~/.claude-secrets` and then exec the real MCP server. Claude Desktop's config points to these wrappers instead of hardcoding tokens.

This approach works on any Unix-like system (Linux, macOS). The secrets file is equivalent in security posture to `~/.ssh/id_rsa` — protected by file permissions, not encryption. For stronger protection, full-disk encryption (LUKS on Linux, FileVault on macOS) encrypts everything at rest including this file.

**Never:**
- Put tokens directly in `claude_desktop_config.json`
- Commit `~/.claude-secrets` to any repo
- Share `claude_desktop_config.json` without checking it for embedded keys first

## Daily workflow

The Cowork task runs automatically on schedule. After it completes:

1. Open `job_dashboard.html` in your browser
2. Review new listings (sorted by match score by default)
3. Mark each as: **Interested / Viewed / Hidden / Applied / Not Interested**
4. Click **Save Evaluations** to persist to `job_evaluations.json`

## Dashboard features

The dashboard is a self-contained HTML file with no server dependency for viewing (only `eval_server.py` is needed to save evaluations back to disk).

- **Search** — free-text filter across title, company, and location
- **Source filter** — show only LinkedIn, Indeed, BioSpace, etc.
- **Sort** — by score, found date, first notified date, source, company, or evaluation status; click column headers to sort
- **Evaluation status filter** — show only Interested, Viewed, Applied, Hidden, or Unseen jobs
- **Column filters** — include/exclude rules per column (e.g. exclude company "Staffing Co", include location "Seattle")
- **Named presets** — save and restore complete filter states by name; presets are persisted to `job_presets.json` via eval_server
- **Filter state persistence** — your last filter state is restored automatically when you reopen the dashboard
- **First Notified column** — shows the email date the job first appeared, distinct from the date the pipeline first saw it
- **Source badges** — clickable, link directly to the relevant Gmail search for that source
- **Charts** — jobs over time, by source, and top companies
- **Export CSV** — export current evaluation state

## Scripts

### `process_jobs.py`

Reads `/tmp/new_jobs.json` and upserts jobs into `job_search.db`. Handles:
- Two-stage deduplication: exact match on `external_id + source`, then content match on `title + company + location + source` within 30 days (treats reposts as updates rather than new rows)
- Match scoring (0-100) based on title keywords, company type, location, salary
- Seniority classification
- Company table population
- Tag assignment (bioinformatics, machine-learning, clinical, drug-discovery, data-engineering)
- Email and run logging

```bash
python3 ~/Documents/claude_jobhunt/process_jobs.py
```

### `generate_dashboard.py`

Reads `job_search.db` and `job_evaluations.json`, writes `job_dashboard.html`.

```bash
python3 ~/Documents/claude_jobhunt/generate_dashboard.py
```

### `eval_server.py`

Local HTTP server on `localhost:7432`. Provides two services to the dashboard:
- `GET/POST /evals` — read and write `job_evaluations.json`
- `GET/POST /presets` — read and write `job_presets.json`
- `GET /health` — connection check used by the dashboard on load

```bash
python3 ~/Documents/claude_jobhunt/eval_server.py
```

### `rebuild_db.py`

Drops and recreates `job_search.db` from `db_dump.sql`. Use for recovery only.

```bash
python3 ~/Documents/claude_jobhunt/rebuild_db.py
```

### `check_dupes.py`

Inspects the database for duplicate or near-duplicate job entries. Useful for auditing deduplication behavior after a run.

### `cleanup_old_jobs.py`

Marks jobs that have not been seen recently as inactive/closed. Run manually when you want to tidy the database.

## Customizing the scoring

The scoring system is the primary thing to adapt for your own job search. Open `process_jobs.py` and look for the `USER CONFIGURATION` block. It contains:

- `TARGET_COMPANIES` — exact company names that get a strong score boost. Add organizations you particularly want to work for.
- `FIELD_KEYWORDS` — keywords in company names that suggest your field (e.g. "therapeutics", "genomics").
- `LOCATION_HUBS` — city/region names that score positively. List places you are willing to work.
- Title keyword lists for your specializations (bioinformatics, ML, clinical, etc.) — adjust to match roles in your field.

Scoring is capped at 100. Current signal weights:

| Signal | Points |
|--------|--------|
| Known target company name | +20 |
| Field keywords in company name | +20 |
| Bioinformatics/genomics keywords in title | +20 |
| ML/data science keywords in title | +15 |
| Specialization keywords in title | +15 |
| Salary >= $150K | +10 |
| Preferred location hub | +15 |
| Clinical/regulatory keywords in title | +10 |
| Senior/director/lead title | +10 |

## Database schema

Main tables: `jobs`, `companies`, `email_log`, `run_log`, `applications`, `tags`, `job_tags`, `job_company_link`, `search_criteria`.

Schema is defined and auto-applied in `process_jobs.py` (SCHEMA constant). See that file for full DDL.

## Backup and recovery

To create a SQL dump:
```bash
sqlite3 ~/Documents/claude_jobhunt/job_search.db .dump > ~/Documents/claude_jobhunt/db_dump.sql
```

To restore from dump:
```bash
python3 ~/Documents/claude_jobhunt/rebuild_db.py
```

## Notes

- After running a Cowork task, start a **new chat session** before using filesystem MCP tools. Cowork may override the filesystem MCP allowed directory to a session sandbox.
- The `/tmp/new_jobs.json` file is a temporary handoff between the Cowork task and `process_jobs.py`. It is not preserved between runs.
- `job_evaluations.json` and `job_presets.json` must be preserved across DB rebuilds — they are independent of the database.
