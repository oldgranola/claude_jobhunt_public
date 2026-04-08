# Cowork Scheduled Task — Daily Job Ingest

This file documents the Claude Desktop Cowork scheduled task that drives the daily job ingest pipeline.

## How to use this file

If the Cowork task is ever lost or needs to be recreated:
1. Open Claude Desktop → Cowork
2. Create a new scheduled task
3. Set the schedule (e.g. daily at a fixed time)
4. Paste the task instructions below verbatim into the task body
5. Ensure the Gmail MCP connector is enabled for the task

## Dependencies

The task requires these MCP servers to be active in the Cowork context:
- **Gmail MCP** — to search and read job alert emails
- **filesystem MCP** — to write `/tmp/new_jobs.json` and read/run scripts via bash

The task also shells out to Python 3 and expects these files to be present at their Cowork session mount path:
- `process_jobs.py`
- `generate_dashboard.py`
- `job_search.db` (created automatically on first run)

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
      "url": "<direct job listing URL>"
    }
  ]
}
```

If no new emails are found, the task writes `{"emails":[],"jobs":[]}`.

## Task instructions (paste verbatim into Cowork)

---

Automated daily job ingest. Execute each step in order. No preamble, no planning — just run the steps.

## STEP 1 — Get already-processed email IDs
Run this bash command and note the JSON list output as SKIP_IDS:

```bash
python3 -c "
import glob, sqlite3, json
paths = glob.glob('/sessions/*/mnt/claude_jobhunt/job_search.db')
if not paths: print('[]'); exit()
conn = sqlite3.connect(paths[0])
try:
    ids = [r[0] for r in conn.execute('SELECT email_id FROM email_log')]
    print(json.dumps(ids))
except: print('[]')
conn.close()
"
```

## STEP 2 — Search Gmail for new job alert emails
Run all four searches in parallel. Combine all results, deduplicate by message_id, skip any already in SKIP_IDS.

- gmail_search_messages: query="from:jobalerts-noreply@linkedin.com newer_than:14d"
- gmail_search_messages: query="from:jobs-listings@linkedin.com newer_than:14d"
- gmail_search_messages: query="from:indeed newer_than:14d"
- gmail_search_messages: query="from:biospace.com OR from:yourmembership.com OR from:postjobfree.com OR subject:(\"job alert\" OR \"now hiring\" OR \"is hiring\" OR \"job opening\" OR \"job recommendation\") newer_than:14d -from:jobalerts-noreply@linkedin.com -from:jobs-listings@linkedin.com -from:indeed"

For each remaining message_id, read the full body with gmail_read_message.

Before extracting, classify the email: if it does not contain actual job listings with titles and apply links, skip it and log it with jobs_extracted=0. Do not attempt to extract jobs from social notifications, security alerts, newsletters without listings, or promotional emails.

## STEP 3 — Extract job data
From each qualifying email body extract all job listings. For each job:
- external_id: LinkedIn → numeric ID from URL path /jobs/view/NNNN/; Indeed → value of jk= param in URL; others → full URL
- source: "linkedin", "indeed", "biospace", "lifesciwa", "postjobfree", or the sender domain if none match
- title, company, location (city/state or "United States" if remote)
- salary_min, salary_max: integers in dollars (null if not shown)
- job_type: "full-time" or "contract" (default "full-time" if not stated)
- work_mode: "remote", "hybrid", "onsite", or null if not stated
- email_date: the email's received_date in YYYY-MM-DDTHH:MM:SS format (same value for all jobs from the same email)
- url: the direct job listing URL

Write /tmp/new_jobs.json in exactly this format:
```json
{
  "emails": [
    {"email_id":"<id>","subject":"<subj>","sender":"<from>","received_date":"<YYYY-MM-DDTHH:MM:SS>","source":"<source>","jobs_extracted":<N>}
  ],
  "jobs": [
    {"external_id":"<id>","source":"<source>","title":"<t>","company":"<co>","location":"<loc>","salary_min":null,"salary_max":null,"job_type":"full-time","work_mode":null,"email_date":"<YYYY-MM-DDTHH:MM:SS>","url":"<url>"}
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
Check that the Gmail MCP connector is authorised and that the query date range (`newer_than:14d`) covers the expected period. If the task has been inactive for more than 14 days, you can temporarily widen it to `newer_than:30d` directly in the Cowork task window.

**process_jobs.py runs but adds 0 jobs**
All emails may already be in `email_log` (SKIP_IDS). Or the emails were classified as non-listing emails (Step 2 filter). Check the `email_log` table and `run_log` for details.

**Dashboard shows stale data**
`generate_dashboard.py` may have failed in Step 4. Run it manually:
```bash
python3 ~/Documents/claude_jobhunt/generate_dashboard.py
```
