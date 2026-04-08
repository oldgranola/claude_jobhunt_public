#!/usr/bin/env python3
"""
process_jobs.py  —  Daily ingest worker for job_search.db
Reads:   /tmp/new_jobs.json   (written by Claude each run)
Updates: job_search.db        (in this script's own directory)
Run:     python3 /path/to/process_jobs.py
"""
import sqlite3, json, os
from datetime import datetime, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
DB  = os.path.join(DIR, 'job_search.db')
IN  = '/tmp/new_jobs.json'

# ── Schema ─────────────────────────────────────────────────────────────────────────────
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, external_id TEXT, source TEXT NOT NULL,
    title TEXT NOT NULL, company TEXT, location TEXT,
    salary_min REAL, salary_max REAL, salary_currency TEXT DEFAULT 'USD',
    job_type TEXT, work_mode TEXT, seniority TEXT, description TEXT, url TEXT,
    date_posted DATE, date_first_seen DATE NOT NULL DEFAULT (date('now')),
    date_last_seen DATE NOT NULL DEFAULT (date('now')), date_closed DATE,
    is_active INTEGER DEFAULT 1, match_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(external_id, source));
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    name_normalized TEXT, industry TEXT, sub_industry TEXT,
    is_target INTEGER DEFAULT 0, notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name_normalized));
CREATE TABLE IF NOT EXISTS email_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email_id TEXT NOT NULL UNIQUE,
    subject TEXT, sender TEXT, received_date TIMESTAMP, source TEXT,
    jobs_extracted INTEGER DEFAULT 0,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'processed');
CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_type TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP,
    emails_processed INTEGER DEFAULT 0, jobs_added INTEGER DEFAULT 0,
    jobs_updated INTEGER DEFAULT 0, errors TEXT, status TEXT DEFAULT 'running');
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, category TEXT);
CREATE TABLE IF NOT EXISTS job_tags (
    job_id INTEGER NOT NULL, tag_id INTEGER NOT NULL,
    PRIMARY KEY (job_id, tag_id));
CREATE TABLE IF NOT EXISTS job_company_link (
    job_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
    PRIMARY KEY (job_id, company_id));
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'interested', date_applied DATE, notes TEXT,
    resume_version TEXT, cover_letter_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS search_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    criteria_json TEXT NOT NULL, is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_jobs_source         ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_score          ON jobs(match_score);
CREATE INDEX IF NOT EXISTS idx_jobs_date           ON jobs(date_first_seen);
CREATE INDEX IF NOT EXISTS idx_companies_target    ON companies(is_target);
CREATE INDEX IF NOT EXISTS idx_email_source        ON email_log(source);
"""

# ── USER CONFIGURATION ──────────────────────────────────────────────────────────────────────
#
# Edit these three lists to match your target employers and preferred locations.
# All matching is case-insensitive substring matching against job fields.
#
# BIO_NAMES: partial company names you want to prioritize (+20 pts per match)
#   Add any employer you particularly want to see near the top of your dashboard.
#   Partial matches work: 'genentech' matches 'Genentech', 'Roche/Genentech', etc.
#
# BIO_KW: keywords in company names that indicate your target industry (+20 pts)
#   These catch whole categories of employers without listing them individually.
#
# HUBS: city or region keywords for locations you prefer (+15 pts)
#   Use lowercase partial strings: 'boston' matches 'Boston, MA', 'Greater Boston', etc.
#
# The example below is configured for biotech/life-sciences.
# Replace the contents of each set/list with your own values.

BIO_NAMES = {
    # Examples — replace with your own target companies:
    'genentech', 'amgen', 'regeneron', 'pfizer', 'biontech',
    'moderna', 'illumina', '10x genomics', 'pacific biosciences',
    'alnylam', 'eurofins',
}

BIO_KW = [
    # Examples — keywords that identify your target sector in company names:
    'biotech', 'pharma', 'therapeutics', 'life sciences', 'biosciences',
    'research institute', 'cancer center', 'medical center',
]

HUBS = [
    # Examples — replace with your preferred cities or regions:
    'south san francisco', 'san diego', 'boston', 'cambridge',
    'new york', 'research triangle',
]

# ── Scoring keyword lists — adjust to your discipline ────────────────────────────
# These keyword lists drive title-based scoring. Edit to match your field.
BIOINFO   = ['bioinformatics', 'genomics', 'sequencing', 'ngs', 'rna-seq',
             'proteomics', 'computational biology', 'omics', 'single cell']
ML        = ['machine learning', 'deep learning', 'neural', 'nlp', 'llm',
             'applied scientist', 'applied science', 'data scientist', 'reinforcement']
DRUGDISC  = ['drug discovery', 'bioassay', 'cell culture', 'crispr', 'antibody',
             'oncology', 'ihc', 'cdx', 'assay development', 'in vitro', 'mab']
CLINICAL  = ['clinical research', 'clinical trial', 'clinical scientist',
             'cra ', 'crc ', 'gcp', 'regulatory affairs']
SENIOR    = ['senior', 'principal', 'director', 'lead ', 'staff ',
             'head of', 'vp ', 'vice president']

# Tags assigned to jobs based on title/company keywords
TAG_RULES = {
    'bioinformatics':   ['bioinformatics', 'genomics', 'sequencing', 'ngs', 'rna-seq', 'proteomics', 'computational biology'],
    'machine-learning': ['machine learning', 'deep learning', 'neural', 'nlp', 'llm', 'applied scientist', 'data scientist'],
    'clinical':         ['clinical research', 'clinical trial', 'clinical scientist', 'cra ', 'gcp'],
    'drug-discovery':   ['drug discovery', 'bioassay', 'cell culture', 'crispr', 'antibody', 'oncology', 'ihc', 'cdx'],
    'data-engineering': ['data engineer', 'etl', 'pipeline', 'spark', 'databricks', 'snowflake'],
}
# ─────────────────────────────────────────────────────────────────────────────────

conn = sqlite3.connect(DB)
conn.executescript(SCHEMA)

if not os.path.exists(IN):
    print("No /tmp/new_jobs.json — nothing to process")
    conn.close(); exit(0)

data     = json.load(open(IN))
new_jobs = data.get('jobs', [])
emails   = data.get('emails', [])

def score(title, company, location, smin, smax):
    s = 0
    t, c, l = (title or '').lower(), (company or '').lower(), (location or '').lower()
    if any(k in c for k in BIO_NAMES) or any(k in c for k in BIO_KW): s += 20
    if any(k in t for k in BIOINFO):   s += 20
    if any(k in t for k in ML):        s += 15
    if any(k in t for k in DRUGDISC):  s += 15
    if any(k in t for k in CLINICAL):  s += 10
    if any(k in t for k in SENIOR):    s += 10
    if smax and smax >= 150000:        s += 10
    if any(k in l for k in HUBS):      s += 15
    return min(s, 100)

def seniority(t):
    t = (t or '').lower()
    for keys, val in [
        (['director', 'vp ', 'vice president', 'head of'], 'director'),
        (['principal', 'staff '],                          'principal'),
        (['senior', 'sr.', 'sr '],                        'senior'),
        (['associate', 'coordinator', 'technician', 'assistant'], 'entry-mid'),
    ]:
        if any(k in t for k in keys): return val
    return 'mid'

def is_biotech(name):
    n = (name or '').lower()
    return any(k in n for k in BIO_NAMES) or any(k in n for k in BIO_KW)

now   = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

tag_ids = {}
for tag_name in TAG_RULES:
    row = conn.execute("SELECT id FROM tags WHERE name=?", (tag_name,)).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO tags(name,category) VALUES(?,?)", (tag_name, 'domain'))
    tag_ids[tag_name] = conn.execute("SELECT id FROM tags WHERE name=?", (tag_name,)).fetchone()[0]

added = updated = 0
for j in new_jobs:
    ext_id = str(j.get('external_id') or j.get('url', ''))
    source = j.get('source', 'unknown')
    title  = j.get('title', '')
    co     = j.get('company', '')
    loc    = j.get('location', '')
    smin   = j.get('salary_min'); smax = j.get('salary_max')
    url    = j.get('url', '')
    ms     = score(title, co, loc, smin, smax)
    sen    = seniority(title)

    existing = conn.execute(
        "SELECT id FROM jobs WHERE external_id=? AND source=?", (ext_id, source)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE jobs SET date_last_seen=?,match_score=?,updated_at=? WHERE id=?",
            (today, ms, now, existing[0])
        )
        job_id = existing[0]; updated += 1
    else:
        raw_email_date = j.get('email_date', '')
        date_posted = raw_email_date[:10] if raw_email_date else None

        cur = conn.execute("""
            INSERT INTO jobs(external_id,source,title,company,location,
                salary_min,salary_max,job_type,work_mode,url,
                date_posted,date_first_seen,date_last_seen,is_active,match_score,seniority,
                created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
            (ext_id, source, title, co, loc, smin, smax,
             j.get('job_type', 'full-time'), j.get('work_mode'),
             url, date_posted, today, today, ms, sen, now, now)
        )
        job_id = cur.lastrowid; added += 1

    cnorm = (co or '').lower().strip()
    if cnorm:
        row = conn.execute("SELECT id FROM companies WHERE name_normalized=?", (cnorm,)).fetchone()
        if row:
            co_id = row[0]
        else:
            conn.execute(
                "INSERT OR IGNORE INTO companies(name,name_normalized,is_target,created_at,updated_at) VALUES(?,?,?,?,?)",
                (co.strip(), cnorm, 1 if is_biotech(co) else 0, now, now)
            )
            co_id = conn.execute("SELECT id FROM companies WHERE name_normalized=?", (cnorm,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO job_company_link(job_id,company_id) VALUES(?,?)", (job_id, co_id))

    txt = (title + ' ' + co).lower()
    for tag_name, kws in TAG_RULES.items():
        if any(kw in txt for kw in kws):
            conn.execute("INSERT OR IGNORE INTO job_tags(job_id,tag_id) VALUES(?,?)",
                         (job_id, tag_ids[tag_name]))

for e in emails:
    conn.execute("""
        INSERT OR IGNORE INTO email_log
            (email_id,subject,sender,received_date,source,jobs_extracted,processed_at,status)
        VALUES(?,?,?,?,?,?,?,?)""",
        (e['email_id'], e.get('subject'), e.get('sender'), e.get('received_date'),
         e.get('source'), e.get('jobs_extracted', 0), now, 'processed')
    )

conn.execute("""
    INSERT INTO run_log(run_type,started_at,completed_at,emails_processed,jobs_added,jobs_updated,status)
    VALUES(?,?,?,?,?,?,?)""",
    ('daily_ingest', now, now, len(emails), added, updated, 'completed')
)

conn.commit(); conn.close()
print(f"process_jobs: +{added} added, ~{updated} updated, {len(emails)} emails → {DB}")
