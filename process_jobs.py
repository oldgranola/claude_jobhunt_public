#!/usr/bin/env python3
"""
process_jobs.py  —  Daily ingest worker for job_search.db
Reads:   /tmp/new_jobs.json   (written by Claude each run)
Updates: job_search.db        (in this script's own directory = the mount)
Run:     python3 /path/to/process_jobs.py
"""
import sqlite3, json, os, hashlib
from datetime import datetime, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
DB  = os.path.join(DIR, 'job_search.db')
IN  = '/tmp/new_jobs.json'

# ── Schema ────────────────────────────────────────────────────────────────────
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

conn = sqlite3.connect(DB)
conn.executescript(SCHEMA)

if not os.path.exists(IN):
    print("No /tmp/new_jobs.json — nothing to process")
    conn.close(); exit(0)

data     = json.load(open(IN))
new_jobs = data.get('jobs', [])
emails   = data.get('emails', [])

# ─────────────────────────────────────────────────────────────────────────────
# USER CONFIGURATION — customize these for your own job search
# ─────────────────────────────────────────────────────────────────────────────

# Exact company names (lowercase) that score a strong boost.
# Add organizations you particularly want to work for.
TARGET_COMPANIES = {
    'acme biotherapeutics', 'horizon therapeutics', 'pacific biotech inc',
    'northwest genomics', 'regional medical center', 'university research institute',
    # Add your own target companies here
}

# Keywords in company names suggesting your field.
# Examples below are for biotech/life sciences — adapt as needed.
FIELD_KW = [
    'biotech', 'pharma', 'therapeutics', 'life sciences', 'biosciences',
    'research institute', 'cancer center', 'medical center',
]

# City/region names that score positively for location preference.
# List places you are willing to work (lowercase).
LOCATION_HUBS = [
    'seattle', 'boston', 'san francisco', 'san diego', 'cambridge',
    # Add your preferred locations here
]

# ─────────────────────────────────────────────────────────────────────────────
# Title keyword lists — adjust to match roles in your field
# ─────────────────────────────────────────────────────────────────────────────
BIOINFO   = ['bioinformatics','genomics','sequencing','ngs','rna-seq',
             'proteomics','computational biology','omics','single cell']
ML        = ['machine learning','deep learning','neural','nlp','llm',
             'applied scientist','applied science','data scientist','reinforcement']
DRUGDISC  = ['drug discovery','bioassay','cell culture','crispr','antibody',
             'oncology','ihc','cdx','assay development','in vitro','mab']
CLINICAL  = ['clinical research','clinical trial','clinical scientist',
             'cra ','crc ','gcp','regulatory affairs']
SENIOR    = ['senior','principal','director','lead ','staff ',
             'head of','vp ','vice president']
TAG_RULES = {
    'bioinformatics':   ['bioinformatics','genomics','sequencing','ngs','rna-seq','proteomics','computational biology'],
    'machine-learning': ['machine learning','deep learning','neural','nlp','llm','applied scientist','data scientist'],
    'clinical':         ['clinical research','clinical trial','clinical scientist','cra ','gcp'],
    'drug-discovery':   ['drug discovery','bioassay','cell culture','crispr','antibody','oncology','ihc','cdx'],
    'data-engineering': ['data engineer','etl','pipeline','spark','databricks','snowflake'],
}

# ─────────────────────────────────────────────────────────────────────────────
# END USER CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Aliases for backward compatibility with scoring function
BIO_NAMES = TARGET_COMPANIES
BIO_KW    = FIELD_KW
HUBS      = LOCATION_HUBS

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
        (['director','vp ','vice president','head of'], 'director'),
        (['principal','staff '],                        'principal'),
        (['senior','sr.','sr '],                        'senior'),
        (['associate','coordinator','technician','assistant'], 'entry-mid'),
    ]:
        if any(k in t for k in keys): return val
    return 'mid'

def is_biotech(name):
    n = (name or '').lower()
    return any(k in n for k in BIO_NAMES) or any(k in n for k in BIO_KW)


import re as _re
import quopri as _quopri

def _decode_qp_url(s):
    """Decode quoted-printable soft line wraps from Gmail API URLs.
    IMPORTANT: only applies QP byte-decoding when the string actually contains
    QP line-wrap sequences (= at end of line).  Without a line wrap, applying
    quopri.decodestring would misinterpret =XX in URL query params (e.g.
    jk=88b5... -> =88 decoded as byte 0x88 -> invalid UTF-8 -> replacement char).
    Leaves %XX percent-encoding intact as it is already valid URL encoding."""
    if not s or not isinstance(s, str):
        return s
    has_qp_wrap = ('=\r\n' in s or '=\n' in s)
    joined = s.replace('=\r\n', '').replace('=\n', '')
    if not has_qp_wrap:
        return joined
    try:
        decoded = _quopri.decodestring(joined.encode('utf-8')).decode('utf-8', errors='replace')
    except Exception:
        decoded = joined
    return decoded

def resolve_job_url(source, raw_urls, fallback_url='', title='', company=''):
    """
    Derive a reliable (url, external_id) pair from raw hrefs.
    Handles quoted-printable encoding from the Gmail API.
    LinkedIn: extract job ID, build canonical URL.
    Indeed: decode QP, pick first href with jk=, use full URL.
      Fallback when jk= extraction fails: generate a stable 8-char MD5 slug
      from title+company so the external_id is consistent across duplicate alerts
      for the same job (rather than using a unique tracking URL as the ID).
    Others: decode QP, use first non-marketing href.
    Returns (url, external_id).
    """
    hrefs = [_decode_qp_url(h) for h in (raw_urls or []) if h and isinstance(h, str)]
    fallback = _decode_qp_url(fallback_url or '')

    if source == 'linkedin':
        for h in hrefs:
            m = _re.search(r'/jobs/view/(\d+)', h)
            if not m:
                m = _re.search(r'/comm/jobs/view/(\d+)', h)
            if m:
                job_id = m.group(1)
                return f'https://www.linkedin.com/jobs/view/{job_id}/', job_id
        m = _re.search(r'/jobs/view/(\d+)', fallback)
        if m:
            job_id = m.group(1)
            return f'https://www.linkedin.com/jobs/view/{job_id}/', job_id
        return fallback, fallback

    if source == 'indeed':
        best_href = None
        for h in (hrefs + ([fallback] if fallback else [])):
            if not h or 'marketing.' in h or 'e3t/Ctc' in h:
                continue
            m = _re.search(r'[?&]jk=([a-f0-9]{10,20})(?:&|$)', h)
            if m:
                jk = m.group(1)
                return f'https://www.indeed.com/viewjob?jk={jk}', jk
            m = _re.search(r'[?&]jk[^a-f0-9]+([a-f0-9]{10,20})(?:&|$)', h)
            if m:
                jk = m.group(1)
                return f'https://www.indeed.com/viewjob?jk={jk}', jk
            if best_href is None:
                best_href = h
        slug_input = (title + company).lower().strip()
        slug = 'indeed-' + hashlib.md5(slug_input.encode()).hexdigest()[:8]
        return (best_href or fallback or ''), slug

    for h in hrefs:
        if 'marketing.' in h or 'e3t/Ctc' in h:
            continue
        return h, h
    return fallback, fallback

def normalize_source(source, sender=''):
    """Canonicalize source to linkedin/indeed/known-source or sender domain."""
    s = (source or '').lower()
    sd = (sender or '').lower()
    if 'linkedin' in s or 'linkedin' in sd:
        return 'linkedin'
    if 'indeed' in s or 'indeed' in sd:
        return 'indeed'
    if 'yourmembership' in s or 'yourmembership' in sd:
        return 'lifesciwa'
    if 'biospace' in s or 'biospace' in sd:
        return 'biospace'
    return s or 'unknown'

now   = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

# Ensure tags exist
tag_ids = {}
for tag_name in TAG_RULES:
    row = conn.execute("SELECT id FROM tags WHERE name=?", (tag_name,)).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO tags(name,category) VALUES(?,?)", (tag_name,'domain'))
    tag_ids[tag_name] = conn.execute("SELECT id FROM tags WHERE name=?", (tag_name,)).fetchone()[0]

added = updated = content_deduped = 0
for j in new_jobs:
    source   = normalize_source(j.get('source',''), j.get('sender',''))
    raw_urls = j.get('email_html_urls') or []
    title    = j.get('title','')
    co       = j.get('company','')
    loc      = j.get('location','')

    url, ext_id = resolve_job_url(source, raw_urls, j.get('url','') or j.get('external_id',''),
                                  title=title, company=co)
    smin     = j.get('salary_min'); smax = j.get('salary_max')
    ms      = score(title, co, loc, smin, smax)
    sen     = seniority(title)
    email_dt = j.get('email_date', '') or ''

    # Step 1: exact match on external_id + source
    existing = conn.execute(
        "SELECT id FROM jobs WHERE external_id=? AND source=?", (ext_id, source)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE jobs SET date_last_seen=?,match_score=?,updated_at=? WHERE id=?",
            (today, ms, now, existing[0])
        )
        job_id = existing[0]; updated += 1
        continue

    # Step 2: content dedup — same title+company+location+source within 30 days
    content_match = conn.execute("""
        SELECT id FROM jobs
        WHERE lower(trim(title))    = lower(trim(?))
          AND lower(trim(company))  = lower(trim(?))
          AND lower(trim(location)) = lower(trim(?))
          AND source = ?
          AND date_first_seen >= date('now', '-30 days')
        ORDER BY date_first_seen ASC
        LIMIT 1
    """, (title, co, loc, source)).fetchone()

    if content_match:
        conn.execute(
            "UPDATE jobs SET date_last_seen=?,match_score=?,updated_at=? WHERE id=?",
            (today, ms, now, content_match[0])
        )
        job_id = content_match[0]; content_deduped += 1
        continue

    # Step 3: genuinely new job — insert
    raw_email_date = j.get('email_date', '')
    date_posted = raw_email_date[:10] if raw_email_date else None

    cur = conn.execute("""
        INSERT INTO jobs(external_id,source,title,company,location,
            salary_min,salary_max,job_type,work_mode,url,
            date_posted,date_first_seen,date_last_seen,is_active,match_score,seniority,
            email_date,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)""",
        (ext_id, source, title, co, loc, smin, smax,
         j.get('job_type','full-time'), j.get('work_mode'),
         url, date_posted, today, today, ms, sen,
         email_dt[:10] if email_dt else None, now, now)
    )
    job_id = cur.lastrowid; added += 1

    # Company
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

    # Tags
    txt = (title + ' ' + co).lower()
    for tag_name, kws in TAG_RULES.items():
        if any(kw in txt for kw in kws):
            conn.execute("INSERT OR IGNORE INTO job_tags(job_id,tag_id) VALUES(?,?)",
                         (job_id, tag_ids[tag_name]))

# Log emails
for e in emails:
    conn.execute("""
        INSERT OR IGNORE INTO email_log
            (email_id,subject,sender,received_date,source,jobs_extracted,processed_at,status)
        VALUES(?,?,?,?,?,?,?,?)""",
        (e['email_id'], e.get('subject'), e.get('sender'), e.get('received_date'),
         normalize_source(e.get('source',''), e.get('sender','')),
         e.get('jobs_extracted', 0), now, 'processed')
    )

# Run log
conn.execute("""
    INSERT INTO run_log(run_type,started_at,completed_at,emails_processed,jobs_added,jobs_updated,status)
    VALUES(?,?,?,?,?,?,?)""",
    ('daily_ingest', now, now, len(emails), added, updated + content_deduped, 'completed')
)

conn.commit(); conn.close()
print(f"process_jobs: +{added} added, ~{updated} exact-updated, "
      f"~{content_deduped} content-deduped, {len(emails)} emails -> {DB}")
