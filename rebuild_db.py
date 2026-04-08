#!/usr/bin/env python3
"""
Rebuild job_search.db from db_dump.sql.
Run: python3 ~/Documents/claude_jobhunt/rebuild_db.py
"""
import sqlite3
import os

DIR = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(DIR, 'db_dump.sql')
DB   = os.path.join(DIR, 'job_search.db')

if os.path.exists(DB):
    os.remove(DB)

with open(DUMP, 'r') as f:
    sql = f.read()

conn = sqlite3.connect(DB)
conn.executescript(sql)
conn.close()

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM jobs")
jobs = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM companies")
companies = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM email_log")
emails = cur.fetchone()[0]
conn.close()

print(f"Database rebuilt: {DB}")
print(f"  Jobs: {jobs}, Companies: {companies}, Emails processed: {emails}")
