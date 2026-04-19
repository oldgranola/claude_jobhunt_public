# Cowork Scheduled Task — Daily Job Ingest

This file documents the Claude Desktop Cowork scheduled task that drives the daily job ingest pipeline.

## How to use this file

If the Cowork task is ever lost or needs to be recreated:
1. Open Claude Desktop -> Cowork
2. Create a new scheduled task
3. Set the schedule (e.g. daily at a fixed time)
4. Paste the task instructions below verbatim into the task body
5. Ensure the gmail-raw MCP connector is enabled for the task

## Dependencies

The task requires these MCP servers to be active in the Cowork context:
- **gmail-raw MCP** — to search and read job alert emails (format=raw, correct QP decoding)
- **filesystem MCP** — to write `/tmp/new_jobs.json` and read/run scripts via bash

The task also shells out to Python 3 and expects these files to be present at their Cowork session mount path:
- `process_jobs.py`
- `generate_dashboard.py`
- `job_search.db` (created automatically on first run)

## Why gmail-raw instead of the Google Gmail MCP

The Google Gmail MCP uses the Gmail API's `format=full`, which pre-decodes quoted-printable
content server-side. This corrupts URLs containing sequences like `=d5` — the API interprets
them as QP-escaped bytes and consumes the hex digits, truncating jk= parameters in Indeed
job alert URLs (e.g. `d58b5cd1ea1ee67b` -> `8b5cd1ea1ee67b`).

The gmail-raw MCP uses `format=raw`, returning the untouched RFC 2822 message, then applies
Python's `quopri` module for correct decoding. All href values in the HTML body are intact.

## Data contract

The task produces `/tmp/new_jobs.json` in this exact format, which `process_jobs.py` reads:

```json
{
  "emails": [
    {
      "email_id": "<gmail message id>",
      "subject": "<email subject>",
      "sender": "<from address>",
      "received_date": "<YYYY-MM-DDTHH:MM:SS>",
      "source": "<linkedin|indeed|biospace|lifesciwa|postjobfree>",
      "jobs_extracted": 3
    }
  ],
  "jobs": [
    {
      "external_id": "<numeric LinkedIn ID, jk= param for Indeed, or full URL>",
      "source": "<linkedin|indeed|biospace|lifesciwa|postjobfree|sender domain>",
      "title": "<job title>",
      "company": "<company name>",
      "location": "<city, state or 'United States' if remote>",
      "salary_min": null,
      "salary_max": null,
      "job_type": "full-time",
      "work_mode": "<remote|hybrid|onsite|null>",
      "email_date": "<YYYY-MM-DDTHH:MM:SS>",
      "url": "<any url is fine, pipeline will resolve>",
      "email_html_urls": ["<exact raw href from email HTML for this job>", "<second href if present>"]
    }
  ]
}
```

If no new emails are found, the task writes `{"emails":[],"jobs":[]}`.

## Task instructions (paste verbatim into Cowork)

---

Automated daily job ingest. Execute each step in order. No preamble, no planning — just run the steps.

## STEP 1 — Get already-processed email IDs and compute search window
Run this bash command. It outputs two values: SKIP_IDS (JSON list of already-processed email IDs) and SINCE_DATE (the Gmail search start date in YYYY/MM/DD format). Note both values.

```bash
python3 -c "
import glob, sqlite3, json
from datetime import datetime, timezone, timedelta

paths = glob.glob('/sessions/*/mnt/claude_jobhunt/job_search.db')
if not paths:
    print('SKIP_IDS=[]')
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y/%m/%d')
    print('SINCE_DATE=' + since)
    exit()

conn = sqlite3.connect(paths[0])
try:
    ids = [r[0] for r in conn.execute('SELECT email_id FROM email_log')]
    print('SKIP_IDS=' + json.dumps(ids))
except:
    print('SKIP_IDS=[]')

try:
    last = conn.execute(
        'SELECT completed_at FROM run_log WHERE status=\"completed\" ORDER BY id DESC LIMIT 1'
    ).fetchone()
    if last and last[0]:
        last_dt = datetime.fromisoformat(last[0].replace(' ', 'T'))
        days_ago = (datetime.now(timezone.utc) - last_dt.replace(tzinfo=timezone.utc)).days
        lookback = min(days_ago + 2, 14)
    else:
        lookback = 14
except:
    lookback = 14

since = (datetime.now(timezone.utc) - timedelta(days=lookback)).strftime('%Y/%m/%d')
print('SINCE_DATE=' + since)
conn.close()
"
```

## STEP 2 — Search Gmail for new job alert emails
Use the gmail-raw MCP for all searches and body retrieval. Run searches in two sequential batches to avoid rate limiting. Use SINCE_DATE from Step 1 in all queries. Combine all results, deduplicate by message_id, skip any already in SKIP_IDS.

**Batch 1** — run these two in parallel, wait for both to complete before proceeding:
- gmail-raw:search_messages: query="from:jobalerts-noreply@linkedin.com after:SINCE_DATE"
- gmail-raw:search_messages: query="from:jobs-listings@linkedin.com after:SINCE_DATE"

**Batch 2** — run these two in parallel after Batch 1 completes:
- gmail-raw:search_messages: query="from:donotreply@jobalert.indeed.com after:SINCE_DATE"
- gmail-raw:search_messages: query="subject:(\"job alert\" OR \"now hiring\" OR \"is hiring\" OR \"job opening\" OR \"job recommendation\") after:SINCE_DATE -from:jobalerts-noreply@linkedin.com -from:jobs-listings@linkedin.com -from:donotreply@jobalert.indeed.com"

If any search returns an error, retry it once individually before moving on. Do not retry more than once — proceed with whatever results were obtained.

For each remaining message_id, fetch the full decoded HTML body using:
- gmail-raw:get_decoded_email_body(message_id)

This returns a clean, fully decoded HTML string. All href values are intact and correct — no URL reconstruction or jk= guessing is needed.

Before extracting, classify the email: if it does not contain actual job listings with titles and apply links, skip it and log it with jobs_extracted=0. Do not attempt to extract jobs from social notifications, security alerts, newsletters without listings, or promotional emails.

## STEP 3 — Extract job data
From each qualifying email HTML body, extract all job listings. The body is clean decoded HTML — parse href attributes directly from anchor tags.

For each job:
- title, company, location (city/state or "United States" if remote)

  **Company name rules (critical):**
  - NEVER write "Unknown", "unknown", or any placeholder string as the company value. If the company truly cannot be determined, use JSON null — not a string.
  - For Indeed emails: the company name appears as plain text immediately below or beside the job title in each listing block. It is NOT inside the job title anchor tag itself. Look at the surrounding `<span>`, `<div>`, or `<td>` elements adjacent to the title anchor for a text node containing the company name. Indeed job alert emails always include the company name — if you do not see it immediately, examine the raw HTML block for that listing more carefully before giving up.
  - For LinkedIn emails: the company name is typically a separate line of text or a `<span>` element adjacent to the job title link inside each listing card.
  - If after careful inspection a company name genuinely cannot be determined, use null (JSON null), not an empty string, not "Unknown".

- source: normalize using the sender address:
  - sender contains "linkedin" (any variation) -> use exactly "linkedin"
  - sender contains "indeed" (any variation) -> use exactly "indeed"
  - sender contains "yourmembership" (any variation) -> use exactly "lifesciwa"
  - sender contains "biospace" (any variation) -> use exactly "biospace"
  - otherwise -> use the sender domain (e.g. "postjobfree.com")
  - never invent suffixes or variants like "linkedin-jobalerts", "linkedin_jymbii", "indeed-jobalerts"
- salary_min, salary_max: integers in dollars (null if not shown)
- job_type: "full-time" or "contract" (default "full-time" if not stated)
- work_mode: "remote", "hybrid", "onsite", or null if not stated
- email_date: the email received_date in YYYY-MM-DDTHH:MM:SS format (same value for all jobs from the same email)
- email_html_urls: extract href attribute values directly from the anchor tags in the HTML. These are clean decoded URLs — copy them exactly as they appear.

  **For LinkedIn**: Copy the href from the anchor tag wrapping the job title. It will be a linkedin.com/comm/jobs/view/NNNNNNNN/... URL. Use this as email_html_urls[0]. The pipeline extracts the numeric job ID and builds a canonical URL.

  **For Indeed**: Copy the href from the anchor tag wrapping the job title. It will be a clean https://www.indeed.com/rc/clk/dl?jk=XXXXXXXXXXXXXXXX&... URL with the full 16-character jk= value intact. Use this as email_html_urls[0]. The pipeline extracts jk= and builds a canonical viewjob URL.

  **For BioSpace**: Skip marketing.biospace.com/e3t/... redirect hrefs — only include jobs.biospace.com hrefs.

  **For all sources**: If a job has two hrefs (e.g. one on the company name and one on the job title), include both in email_html_urls. The pipeline uses the first one that matches.

  If you cannot find a href for a job, leave email_html_urls as [].

- external_id: for LinkedIn use the numeric job ID from the URL path. For Indeed use the jk= value. For others use the full URL. The pipeline will resolve it from email_html_urls anyway.
- url: same as external_id. The pipeline resolves the real canonical URL from email_html_urls.

Write /tmp/new_jobs.json in exactly this format:
```json
{
  "emails": [
    {"email_id":"<id>","subject":"<subj>","sender":"<from>","received_date":"<YYYY-MM-DDTHH:MM:SS>","source":"<source>","jobs_extracted":<N>}
  ],
  "jobs": [
    {"external_id":"<id>","source":"<source>","title":"<t>","company":"<co>","location":"<loc>","salary_min":null,"salary_max":null,"job_type":"full-time","work_mode":null,"email_date":"<YYYY-MM-DDTHH:MM:SS>","url":"<url>","email_html_urls":["<exact href from email HTML>"]}
  ]
}
```
If no new emails were found, write `{"emails":[],"jobs":[]}` to /tmp/new_jobs.json.

## STEP 4 — Run ingest and dashboard scripts
```bash
python3 $(ls /sessions/*/mnt/claude_jobhunt/process_jobs.py 2>/dev/null | head -1) && python3 $(ls /sessions/*/mnt/claude_jobhunt/generate_dashboard.py 2>/dev/null | head -1)
```

## STEP 5 — Verify and report
```bash
python3 -c "
import glob, sqlite3
paths = glob.glob('/sessions/*/mnt/claude_jobhunt/job_search.db')
if not paths: print('ERROR: DB not found'); exit()
conn = sqlite3.connect(paths[0])
total = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
run   = conn.execute('SELECT completed_at,jobs_added,jobs_updated,emails_processed FROM run_log ORDER BY id DESC LIMIT 1').fetchone()
by_source = conn.execute('SELECT source,COUNT(*) FROM jobs GROUP BY source').fetchall()
conn.close()
print('Total jobs in DB:', total)
if run: print('Last run: +{} new, ~{} updated, {} emails, at {}'.format(run[1],run[2],run[3],run[0]))
for s,n in by_source: print(' ', s, ':', n, 'jobs')
"
```

Print the run summary. Done.

---

## Troubleshooting

**"DB not found" in Step 1 or Step 5**
The glob `/sessions/*/mnt/claude_jobhunt/job_search.db` finds the DB via Cowork's session mount. If no paths match, the filesystem MCP may not have the project directory mounted. Check the Cowork task's filesystem MCP configuration.

**No emails found despite expecting some**
Check that the gmail-raw MCP is active in the Cowork context and that the query date range covers the expected period. If the task has been inactive for more than 14 days, you can temporarily widen the lookback by editing the `lookback = 14` value in Step 1 directly in the Cowork task window.

**process_jobs.py runs but adds 0 jobs**
All emails may already be in `email_log` (SKIP_IDS). Or the emails were classified as non-listing emails (Step 2 filter). Check the `email_log` table and `run_log` for details.

**Dashboard shows stale data**
`generate_dashboard.py` may have failed in Step 4. Run it manually:
```bash
python3 ~/Documents/claude_jobhunt/generate_dashboard.py
```

**Indeed URLs are broken**
With gmail-raw this should no longer occur — the jk= values are extracted directly from clean HTML hrefs. If a broken URL is seen, check whether the gmail-raw MCP server is running and the token at `~/.gmail_raw_mcp/token.json` is valid. If the token has expired, re-run:
```bash
python3 ~/Documents/gmail_raw_mcp/auth.py
```

**gmail-raw MCP not available in Cowork context**
Ensure the gmail-raw entry is present in `~/.config/Claude/claude_desktop_config.json` and Claude Desktop has been restarted. The Cowork task context inherits MCP servers from the Claude Desktop configuration.
