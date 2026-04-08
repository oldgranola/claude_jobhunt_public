#!/usr/bin/env python3
"""
generate_dashboard.py  —  Build job_dashboard.html from job_search.db
Reads:  job_search.db           (in this script's own directory)
        job_evaluations.json    (your persisted interest/status choices)
Writes: job_dashboard.html      (same directory)
Run:    python3 /path/to/generate_dashboard.py
"""
import sqlite3, json, os
from datetime import datetime, timezone

DIR  = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(DIR, 'job_search.db')
OUT  = os.path.join(DIR, 'job_dashboard.html')
EVAL = os.path.join(DIR, 'job_evaluations.json')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

if os.path.exists(EVAL):
    with open(EVAL) as f:
        evaluations = json.load(f)
else:
    evaluations = {}

total     = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active=1").fetchone()[0]
new_week  = conn.execute("SELECT COUNT(*) FROM jobs WHERE date_first_seen >= date('now','-7 days')").fetchone()[0]
new_today = conn.execute("SELECT COUNT(*) FROM jobs WHERE date_first_seen=date('now')").fetchone()[0]
companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
apps      = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]

by_source = dict(conn.execute(
    "SELECT source,COUNT(*) FROM jobs WHERE is_active=1 GROUP BY source").fetchall())
top_cos   = conn.execute(
    "SELECT company,COUNT(*) n FROM jobs WHERE is_active=1 AND company IS NOT NULL "
    "GROUP BY company ORDER BY n DESC LIMIT 12").fetchall()
by_date   = conn.execute(
    "SELECT date_first_seen,COUNT(*) FROM jobs "
    "GROUP BY date_first_seen ORDER BY date_first_seen").fetchall()

rows = conn.execute("""
    SELECT j.id, j.title, j.company, j.location, j.source, j.work_mode,
           j.salary_min, j.salary_max, j.match_score, j.date_first_seen, j.url, j.seniority,
           MIN(e.received_date) as first_email_date,
           j.source as email_source
    FROM jobs j
    LEFT JOIN email_log e ON e.source = j.source
    WHERE j.is_active=1
    GROUP BY j.id
    ORDER BY j.match_score DESC, j.date_first_seen DESC
""").fetchall()
conn.close()

def sal(lo, hi):
    if lo and hi:
        return '${}K\u2013${}K'.format(int(lo/1000), int(hi/1000))
    return ''

SOURCE_SEARCH = {
    'linkedin':    'https://mail.google.com/mail/u/0/#search/from%3Alinkedin',
    'indeed':      'https://mail.google.com/mail/u/0/#search/from%3Aindeed',
    'biospace':    'https://mail.google.com/mail/u/0/#search/from%3Abiospace.com',
    'lifesciwa':   'https://mail.google.com/mail/u/0/#search/from%3Ayourmembership.com',
    'postjobfree': 'https://mail.google.com/mail/u/0/#search/from%3Apostjobfree.com',
}

def fmt_email_date(dt):
    if not dt:
        return ''
    return str(dt)[:10]

jobs_js = json.dumps([{
    'id': r['id'], 'title': r['title'] or '', 'company': r['company'] or '',
    'location': r['location'] or '', 'source': r['source'],
    'work_mode': r['work_mode'] or '',
    'salary_range': sal(r['salary_min'], r['salary_max']),
    'match_score': int(r['match_score'] or 0),
    'date_found': r['date_first_seen'] or '',
    'first_email_date': fmt_email_date(r['first_email_date']),
    'source_url': SOURCE_SEARCH.get(r['source'], ''),
    'url': r['url'] or '',
    'seniority': r['seniority'] or ''
} for r in rows])

date_labels = json.dumps([d for d, _ in by_date])
date_counts = json.dumps([c for _, c in by_date])
src_labels  = json.dumps(list(by_source.keys()))
src_counts  = json.dumps(list(by_source.values()))
co_labels   = json.dumps([r[0] or 'Unknown' for r in top_cos])
co_counts   = json.dumps([r[1] for r in top_cos])
evals_js    = json.dumps(evaluations)

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;padding:20px}
h1{font-size:26px;color:#f1f5f9;text-align:center;margin-bottom:4px}
.sub{text-align:center;color:#94a3b8;font-size:13px;margin-bottom:22px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin-bottom:22px}
.kpi{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;text-align:center}
.kpi .v{font-size:28px;font-weight:700;color:#38bdf8}
.kpi .l{font-size:12px;color:#94a3b8;margin-top:3px}
.kpi.g .v{color:#4ade80}.kpi.y .v{color:#fbbf24}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px;margin-bottom:22px}
.card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px}
.card h3{color:#f1f5f9;font-size:14px;margin-bottom:12px}
.filters{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:12px;align-items:center}
.filters input,.filters select{background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:7px;padding:6px 10px;font-size:13px}
.filters input{flex:1;min-width:180px}
.cnt{color:#94a3b8;font-size:12px;margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#334155;color:#e2e8f0;padding:8px 10px;text-align:left;cursor:pointer;position:sticky;top:0;white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid #263346;vertical-align:top}
tr:hover td{background:#1a2840}
a{color:#38bdf8;text-decoration:none}a:hover{text-decoration:underline}
.bl{background:#1d4ed8;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px}
.bi{background:#7c3aed;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px}
.bg{background:#065f46;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px}
.bw{background:#92400e;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px}
.bp{background:#831843;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px}
.sb{display:flex;align-items:center;gap:5px}
.sh{background:#4ade80;height:8px;border-radius:4px}
.sm{background:#fbbf24;height:8px;border-radius:4px}
.sl{background:#f87171;height:8px;border-radius:4px}
.foot{text-align:center;color:#475569;font-size:11px;margin-top:18px}
.eval-cell{display:flex;gap:4px;align-items:center;white-space:nowrap}
.ev{border:none;border-radius:4px;padding:3px 7px;font-size:11px;cursor:pointer;opacity:0.35;transition:opacity .15s,transform .1s}
.ev:hover{opacity:0.75}
.ev.active{opacity:1;transform:scale(1.08)}
.ev-yes{background:#15803d;color:#fff}
.ev-no{background:#b91c1c;color:#fff}
.ev-ignore{background:#475569;color:#fff}
.ev-applied{background:#0369a1;color:#fff}
#savebar{position:fixed;bottom:18px;right:18px;display:flex;gap:8px;z-index:99}
#savebtn{background:#0ea5e9;color:#fff;border:none;border-radius:8px;padding:9px 18px;font-size:13px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.4)}
#savebtn:hover{background:#38bdf8}
#savebtn.saved{background:#16a34a}
#exportbtn{background:#334155;color:#e2e8f0;border:none;border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer}
#exportbtn:hover{background:#475569}
#saveinfo{color:#94a3b8;font-size:11px;align-self:center}
tr.ev-row-ignore td{opacity:0.4}
tr.ev-row-ignore:hover td{opacity:0.7}
"""

JS_STATIC = r"""
const copts = {responsive:true, plugins:{legend:{labels:{color:'#94a3b8'}}}};
function mkLine(id,labels,data){
  new Chart(document.getElementById(id),{type:'line',data:{labels:labels,datasets:[{label:'Jobs',data:data,borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,0.1)',fill:true,tension:0.3}]},options:{...copts,scales:{x:{ticks:{color:'#94a3b8'}},y:{ticks:{color:'#94a3b8'},beginAtZero:true}}}});
}
function mkDonut(id,labels,data){
  new Chart(document.getElementById(id),{type:'doughnut',data:{labels:labels,datasets:[{data:data,backgroundColor:['#38bdf8','#818cf8','#4ade80','#fb923c']}]},options:copts});
}
function mkBar(id,labels,data){
  new Chart(document.getElementById(id),{type:'bar',data:{labels:labels,datasets:[{label:'Jobs',data:data,backgroundColor:'#818cf8'}]},options:{...copts,indexAxis:'y',scales:{x:{ticks:{color:'#94a3b8'},beginAtZero:true},y:{ticks:{color:'#94a3b8'}}}}});
}
mkLine('tc', DATE_LABELS, DATE_COUNTS);
mkDonut('sc', SRC_LABELS, SRC_COUNTS);
mkBar('cc', CO_LABELS, CO_COUNTS);

const SOURCE_COLORS={'linkedin':'bl','indeed':'bi','biospace':'bg','lifesciwa':'bw','postjobfree':'bp'};
function badge(s,url,dt){
  var cls=SOURCE_COLORS[s]||'bi';
  var label=s+(dt?' ('+dt+')':'');
  return url
    ? '<a href="'+url+'" target="_blank"><span class="'+cls+'">'+label+'</span></a>'
    : '<span class="'+cls+'">'+label+'</span>';
}
function sbar(n){var w=Math.max(n,4),c=n>=60?'sh':n>=35?'sm':'sl';return '<div class="sb"><span class="'+c+'" style="width:'+w+'px"></span><span>'+n+'</span></div>';}

const EVALS_EMBEDDED = EVALS_SEED;
const LS_KEY = 'job_evals_v1';

function loadEvals(){
  let merged = Object.assign({}, EVALS_EMBEDDED);
  try{
    var stored = JSON.parse(localStorage.getItem(LS_KEY)||'{}');
    Object.assign(merged, stored);
  }catch(e){}
  return merged;
}
let evals = loadEvals();

function setEval(id, val){
  var key = String(id);
  if(evals[key]===val){ delete evals[key]; }
  else { evals[key]=val; }
  localStorage.setItem(LS_KEY, JSON.stringify(evals));
  var row = document.getElementById('row-'+id);
  if(row){
    row.className = evals[key]==='ignore' ? 'ev-row-ignore' : '';
    ['yes','no','ignore','applied'].forEach(function(v){
      var btn = document.getElementById('ev-'+id+'-'+v);
      if(btn) btn.className = 'ev ev-'+v+(evals[key]===v?' active':'');
    });
  }
  markUnsaved();
}

const SAVE_URL = 'http://localhost:7432/evals';
var unsaved = false;

function checkServer(){
  fetch('http://localhost:7432/health', {signal: AbortSignal.timeout(800)})
    .then(function(r){ if(r.ok) setServerOk(true); })
    .catch(function(){ setServerOk(false); });
}
function setServerOk(ok){
  var info = document.getElementById('saveinfo');
  var btn  = document.getElementById('savebtn');
  if(ok){
    info.textContent = 'Server connected \u2713';
    btn.title = 'Save directly to job_evaluations.json';
  } else {
    info.textContent = 'eval_server not running \u2014 run: python3 eval_server.py';
    info.style.color = '#f87171';
    btn.title = 'Start eval_server.py first';
  }
}
checkServer();

function markUnsaved(){
  unsaved = true;
  document.getElementById('savebtn').textContent = '\ud83d\udcbe Save Evaluations';
  document.getElementById('savebtn').classList.remove('saved');
  document.getElementById('saveinfo').textContent = 'Unsaved changes';
  document.getElementById('saveinfo').style.color = '#fbbf24';
}

function saveEvals(){
  fetch(SAVE_URL, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(evals)
  })
  .then(function(r){ return r.json(); })
  .then(function(data){
    if(data.ok){
      unsaved = false;
      var btn = document.getElementById('savebtn');
      btn.textContent = '\u2713 Saved';
      btn.classList.add('saved');
      var info = document.getElementById('saveinfo');
      info.textContent = data.entries + ' evaluations saved to file';
      info.style.color = '#4ade80';
    }
  })
  .catch(function(){
    var info = document.getElementById('saveinfo');
    info.textContent = 'Save failed \u2014 is eval_server.py running?  (python3 eval_server.py)';
    info.style.color = '#f87171';
  });
}

function exportCSV(){
  var lines=['id,status'];
  Object.keys(evals).forEach(function(k){lines.push(k+','+evals[k]);});
  var blob=new Blob([lines.join('\n')],{type:'text/csv'});
  var a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='job_evaluations.csv';
  a.click();
}

let cur=[...ALL];
function evalBtns(id){
  var k=String(id),cur_ev=evals[k]||'';
  return '<div class="eval-cell">'
    +'<button id="ev-'+id+'-yes"    class="ev ev-yes'    +(cur_ev==='yes'?' active':'')+'" onclick="setEval('+id+',\'yes\')"    title="Interested">Interested</button>'
    +'<button id="ev-'+id+'-no"     class="ev ev-no'     +(cur_ev==='no'?' active':'')+'"  onclick="setEval('+id+',\'no\')"     title="Viewed">Viewed</button>'
    +'<button id="ev-'+id+'-ignore" class="ev ev-ignore' +(cur_ev==='ignore'?' active':'')+' " onclick="setEval('+id+',\'ignore\')" title="Hide">Hide</button>'
    +'<button id="ev-'+id+'-applied" class="ev ev-applied'+(cur_ev==='applied'?' active':'')+' " onclick="setEval('+id+',\'applied\')" title="Applied">Applied</button>'
    +'</div>';
}

function render(jobs){
  document.getElementById('tb').innerHTML=jobs.map(function(j){
    var rowClass=evals[String(j.id)]==='ignore'?'ev-row-ignore':'';
    return '<tr id="row-'+j.id+'" class="'+rowClass+'">'
      +'<td>'+evalBtns(j.id)+'</td>'
      +'<td><a href="'+j.url+'" target="_blank">'+j.title+'</a></td>'
      +'<td>'+j.company+'</td>'
      +'<td>'+j.location+'</td>'
      +'<td>'+badge(j.source,j.source_url,j.first_email_date)+'</td>'
      +'<td>'+(j.work_mode||'\u2014')+'</td>'
      +'<td>'+(j.salary_range||'\u2014')+'</td>'
      +'<td>'+sbar(j.match_score)+'</td>'
      +'<td>'+j.date_found+'</td>'
      +'</tr>';
  }).join('');
  document.getElementById('cnt').textContent=jobs.length+' of '+ALL.length;
}

function doFilter(){
  var q=document.getElementById('si').value.toLowerCase();
  var sf=document.getElementById('sf').value;
  var so=document.getElementById('so').value;
  var se=document.getElementById('se').value;
  cur=ALL.filter(function(j){
    if(q&&!(j.title+' '+j.company+' '+j.location).toLowerCase().includes(q))return false;
    if(sf&&j.source!==sf)return false;
    var ev=evals[String(j.id)]||'';
    if(se==='yes'&&ev!=='yes')return false;
    if(se==='no'&&ev!=='no')return false;
    if(se==='ignore'&&ev!=='ignore')return false;
    if(se==='applied'&&ev!=='applied')return false;
    if(se==='unseen'&&ev!=='')return false;
    if(se==='nothide'&&ev==='ignore')return false;
    return true;
  });
  cur.sort(function(a,b){
    if(so==='score_asc')return a.match_score-b.match_score;
    if(so==='date_desc')return b.date_found.localeCompare(a.date_found);
    if(so==='company_asc')return a.company.localeCompare(b.company);
    return b.match_score-a.match_score;
  });
  render(cur);
}
doFilter();
"""

html = (
    '<!DOCTYPE html><html lang="en"><head>'
    '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">'
    '<title>Job Search Dashboard</title>'
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>'
    '<style>' + CSS + '</style></head><body>'
    '<h1>Job Search Dashboard</h1>'
    '<div class="sub">Updated ' + today + ' \u00b7 LinkedIn &amp; Indeed</div>'
    '<div class="kpis">'
    '<div class="kpi"><div class="v">' + str(total) + '</div><div class="l">Total Jobs</div></div>'
    '<div class="kpi g"><div class="v">' + str(new_week) + '</div><div class="l">New This Week</div></div>'
    '<div class="kpi y"><div class="v">' + str(new_today) + '</div><div class="l">New Today</div></div>'
    '<div class="kpi"><div class="v">' + str(companies) + '</div><div class="l">Companies</div></div>'
    '<div class="kpi"><div class="v">' + str(apps) + '</div><div class="l">Applications</div></div>'
    '</div>'
    '<div class="charts">'
    '<div class="card"><h3>Jobs Over Time</h3><canvas id="tc" height="200"></canvas></div>'
    '<div class="card"><h3>Source</h3><canvas id="sc" height="200"></canvas></div>'
    '<div class="card"><h3>Top Companies</h3><canvas id="cc" height="240"></canvas></div>'
    '</div>'
    '<div class="card">'
    '<h3>All Jobs</h3>'
    '<div class="filters">'
    '<input id="si" placeholder="Search title, company, location\u2026" oninput="doFilter()">'
    '<select id="sf" onchange="doFilter()"><option value="">All Sources</option>'
    '<option>linkedin</option><option>indeed</option><option>biospace</option>'
    '<option>lifesciwa</option><option>postjobfree</option></select>'
    '<select id="so" onchange="doFilter()">'
    '<option value="score_desc">Score \u2193</option>'
    '<option value="score_asc">Score \u2191</option>'
    '<option value="date_desc">Date \u2193</option>'
    '<option value="company_asc">Company A\u2013Z</option>'
    '</select>'
    '<select id="se" onchange="doFilter()">'
    '<option value="">All Statuses</option>'
    '<option value="unseen">Not yet reviewed</option>'
    '<option value="nothide">Hide ignored</option>'
    '<option value="yes">\u2713 Interested</option>'
    '<option value="applied">\u2192 Applied</option>'
    '<option value="no">\u2717 Not interested</option>'
    '<option value="ignore">\u2013 Ignored</option>'
    '</select>'
    '<span class="cnt" id="cnt"></span>'
    '</div>'
    '<div style="overflow-x:auto"><table><thead><tr>'
    '<th>Status</th><th>Title</th><th>Company</th><th>Location</th>'
    '<th>Source (first notified)</th><th>Mode</th><th>Salary</th><th>Score</th><th>Found</th>'
    '</tr></thead><tbody id="tb"></tbody></table></div>'
    '</div>'
    '<div id="savebar">'
    '<span id="saveinfo" style="color:#94a3b8;font-size:11px"></span>'
    '<button id="exportbtn" onclick="exportCSV()">Export CSV</button>'
    '<button id="savebtn" onclick="saveEvals()">\ud83d\udcbe Save Evaluations</button>'
    '</div>'
    '<div class="foot">Auto-generated by Claude \u00b7 ' + today + '</div>'
    '<script>'
    'const ALL=' + jobs_js + ';\n'
    'const DATE_LABELS=' + date_labels + ';\n'
    'const DATE_COUNTS=' + date_counts + ';\n'
    'const SRC_LABELS=' + src_labels + ';\n'
    'const SRC_COUNTS=' + src_counts + ';\n'
    'const CO_LABELS=' + co_labels + ';\n'
    'const CO_COUNTS=' + co_counts + ';\n'
    'const EVALS_SEED=' + evals_js + ';\n'
    + JS_STATIC +
    '</script></body></html>'
)

with open(OUT, 'w') as f:
    f.write(html)

print("generate_dashboard: {} jobs \u2192 {} ({} KB)".format(
    len(rows), OUT, round(len(html)/1024, 1)))
print("  evaluations loaded: {} entries from {}".format(len(evaluations), EVAL))
