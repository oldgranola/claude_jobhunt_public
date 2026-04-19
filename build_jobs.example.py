#!/usr/bin/env python3
"""
build_jobs.example.py  —  Example of the file Claude generates each run.

DO NOT edit or run this file directly. It is documentation only.

Each time the Cowork scheduled task runs, Claude reads your Gmail job alert
emails and generates a fresh build_jobs.py containing the extracted job data
for that run. The file is overwritten on every run and is excluded from git
(see .gitignore). This example shows the structure so you can understand
what Claude is producing and what process_jobs.py expects to receive.

The actual build_jobs.py:
  - Is written by Claude during the Cowork task (Step 3)
  - Contains only the jobs extracted from that run's emails
  - Is executed immediately by process_jobs.py to produce /tmp/new_jobs.json
  - Should never be committed to version control
"""
import json

jobs = []

# === Email abc123def456 (LinkedIn job alert, 2026-01-15T08:30:00) ===
li_date = '2026-01-15T08:30:00'
for eid, title, co, loc, wm in [
    ('1234567890', 'Senior Scientist, Protein Engineering', 'Acme Biotherapeutics', 'Seattle, WA', None),
    ('9876543210', 'Research Associate II, Cell Biology', 'Pacific Biotech Inc', 'Bothell, WA', None),
    ('1122334455', 'Bioinformatics Scientist', 'Northwest Genomics', 'United States', 'remote'),
]:
    jobs.append({
        'external_id': eid,
        'source': 'linkedin',
        'title': title,
        'company': co,
        'location': loc,
        'salary_min': None,
        'salary_max': None,
        'job_type': 'full-time',
        'work_mode': wm,
        'email_date': li_date,
        'url': f'https://www.linkedin.com/jobs/view/{eid}/',
        'email_html_urls': [f'https://www.linkedin.com/comm/jobs/view/{eid}/?trackingId=example']
    })

# === Email fedcba987654 (Indeed alert, 2026-01-15T07:45:00) ===
ind_date = '2026-01-15T07:45:00'
for eid, title, co, loc, smin, smax, jtype in [
    ('a1b2c3d4e5f6a7b8', 'Principal Scientist, Drug Discovery', 'Horizon Therapeutics', 'Seattle, WA', 140000, 180000, 'full-time'),
    ('b2c3d4e5f6a7b8c9', 'Research Scientist I, Immunology', 'Regional Medical Center', 'Seattle, WA', 75000, 95000, 'full-time'),
    ('c3d4e5f6a7b8c9d0', 'Clinical Research Coordinator', 'University Research Institute', 'Seattle, WA', 55000, 70000, 'full-time'),
]:
    jobs.append({
        'external_id': eid,
        'source': 'indeed',
        'title': title,
        'company': co,
        'location': loc,
        'salary_min': smin,
        'salary_max': smax,
        'job_type': jtype,
        'work_mode': None,
        'email_date': ind_date,
        'url': f'https://www.indeed.com/viewjob?jk={eid}',
        'email_html_urls': [f'https://www.indeed.com/rc/clk/dl?jk={eid}&from=ja']
    })

emails = [
    {
        'email_id': 'abc123def456',
        'subject': 'Acme Biotherapeutics is hiring a Senior Scientist. 2 more jobs for you.',
        'sender': 'jobs-listings@linkedin.com',
        'received_date': '2026-01-15T08:30:00',
        'source': 'linkedin',
        'jobs_extracted': 3
    },
    {
        'email_id': 'fedcba987654',
        'subject': 'Horizon Therapeutics is hiring. 5 more scientist jobs in Seattle, WA.',
        'sender': 'donotreply@jobalert.indeed.com',
        'received_date': '2026-01-15T07:45:00',
        'source': 'indeed',
        'jobs_extracted': 3
    },
]

data = {'emails': emails, 'jobs': jobs}
with open('/tmp/new_jobs.json', 'w') as f:
    json.dump(data, f, indent=2)
print(f'Written: {len(emails)} emails, {len(jobs)} job entries to /tmp/new_jobs.json')
