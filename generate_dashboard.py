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

# ── Load persisted evaluations ────────────────────────────────────────────────
if os.path.exists(EVAL):
    with open(EVAL) as f:
        evaluations = json.load(f)
else:
    evaluations = {}

# ── Stats ──────────────────────────────────────────────────────────────────────
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

# ── Build JS data ──────────────────────────────────────────────────────────────
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

evals_js = json.dumps(evaluations)

# ── HTML ───────────────────────────────────────────────────────────────────────
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
.filters{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:8px;align-items:center}
.filters input,.filters select{background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:7px;padding:6px 10px;font-size:13px}
.filters input{flex:1;min-width:180px}
.cnt{color:#94a3b8;font-size:12px;margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#334155;color:#e2e8f0;padding:8px 10px;text-align:left;position:sticky;top:0;white-space:nowrap}
th.sortable{cursor:pointer}
th.sortable:hover{background:#3d4f6b}
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
.ev-viewed{background:#0f766e;color:#fff}
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
th.sort-asc::after{content:' \u25b2';font-size:10px}
th.sort-desc::after{content:' \u25bc';font-size:10px}
#colfilter-panel{margin-bottom:10px}
#colfilter-toggle{background:none;border:1px solid #475569;border-radius:7px;color:#94a3b8;font-size:12px;padding:4px 10px;cursor:pointer;margin-bottom:6px}
#colfilter-toggle:hover{color:#e2e8f0;border-color:#94a3b8}
#colfilter-toggle.has-rules{color:#fbbf24;border-color:#fbbf24}
#colfilter-body{display:none;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px;margin-bottom:6px}
#colfilter-body.open{display:block}
.cf-row{display:flex;gap:6px;align-items:center;margin-bottom:6px}
.cf-row select,.cf-row input{background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:6px;padding:4px 8px;font-size:12px}
.cf-row input{flex:1;min-width:120px}
.cf-rm{background:none;border:none;color:#f87171;font-size:15px;cursor:pointer;padding:0 4px;line-height:1}
.cf-rm:hover{color:#fff}
#cf-add{background:#1e293b;border:1px solid #475569;border-radius:6px;color:#94a3b8;font-size:12px;padding:4px 10px;cursor:pointer}
#cf-add:hover{color:#e2e8f0}
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
function badge(s,url){
  var cls=SOURCE_COLORS[s]||'bi';
  return url
    ? '<a href="'+url+'" target="_blank"><span class="'+cls+'">'+s+'</span></a>'
    : '<span class="'+cls+'">'+s+'</span>';
}
function sbar(n){var w=Math.max(n,4),c=n>=60?'sh':n>=35?'sm':'sl';return '<div class="sb"><span class="'+c+'" style="width:'+w+'px"></span><span>'+n+'</span></div>';}

// ── Evaluation state ──────────────────────────────────────────────────────────
// Statuses: applied | yes | viewed | '' (unseen) | no | ignore
// Sort order (best first): applied=0, yes=1, viewed=2, ''=3, no=4, ignore=5
const EVAL_ORDER = {applied:0, yes:1, viewed:2, '':3, no:4, ignore:5};

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

function evalOrder(id){
  var v = evals[String(id)] || '';
  return EVAL_ORDER[v] !== undefined ? EVAL_ORDER[v] : 3;
}

function setEval(id, val){
  var key = String(id);
  if(evals[key] === val){ delete evals[key]; }
  else { evals[key] = val; }
  localStorage.setItem(LS_KEY, JSON.stringify(evals));
  markUnsaved();
  doFilter();
}

// ── Save ──────────────────────────────────────────────────────────────────────
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
    info.textContent = 'Save failed \u2014 is eval_server.py running?';
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

// ── Column header click-to-sort ───────────────────────────────────────────────
const TH_SORT = {
  'th-status':    ['status_asc',    'status_desc'],
  'th-source':    ['source_asc',    'source_desc'],
  'th-notified':  ['notified_desc', 'notified_asc'],
  'th-score':     ['score_desc',    'score_asc'],
  'th-found':     ['date_desc',     'date_asc'],
  'th-company':   ['company_asc',   'company_desc'],
};

function thClick(thId){
  var so = document.getElementById('so');
  var pair = TH_SORT[thId];
  if(!pair) return;
  so.value = (so.value === pair[0]) ? pair[1] : pair[0];
  updateThIndicators();
  doFilter();
}

function updateThIndicators(){
  var so = document.getElementById('so').value;
  Object.keys(TH_SORT).forEach(function(id){
    var th = document.getElementById(id);
    if(!th) return;
    var pair = TH_SORT[id];
    th.classList.remove('sort-asc','sort-desc');
    if(so === pair[0])      th.classList.add(pair[0].endsWith('_asc') ? 'sort-asc' : 'sort-desc');
    else if(so === pair[1]) th.classList.add(pair[1].endsWith('_asc') ? 'sort-asc' : 'sort-desc');
  });
}

// ── Column keyword filters ────────────────────────────────────────────────────
const CF_LS_KEY = 'job_col_filters_v1';
var colFilters = [];

function loadColFilters(){
  try{ colFilters = JSON.parse(localStorage.getItem(CF_LS_KEY)||'[]'); }
  catch(e){ colFilters=[]; }
  renderColFilters();
}

const CF_COLS = [
  ['Title',     'title'],
  ['Company',   'company'],
  ['Location',  'location'],
  ['Source',    'source'],
  ['Work Mode', 'work_mode'],
  ['Salary',    'salary_range'],
];

function saveColFilters(){
  localStorage.setItem(CF_LS_KEY, JSON.stringify(colFilters));
  updateCFToggleStyle();
  doFilter();
}

function addColFilter(){
  colFilters.push({col:'company', mode:'exc', kw:''});
  renderColFilters();
  var rows = document.querySelectorAll('.cf-row');
  if(rows.length) rows[rows.length-1].querySelector('input').focus();
}

function removeColFilter(i){
  colFilters.splice(i,1);
  renderColFilters();
  saveColFilters();
}

function renderColFilters(){
  var body = document.getElementById('cf-rows');
  body.innerHTML = colFilters.map(function(r,i){
    var colOpts = CF_COLS.map(function(c){
      return '<option value="'+c[1]+'"'+(r.col===c[1]?' selected':'')+'>'+c[0]+'</option>';
    }).join('');
    return '<div class="cf-row" id="cfrow-'+i+'">'
      +'<select onchange="cfSet('+i+',\'col\',this.value)">'+colOpts+'</select>'
      +'<select onchange="cfSet('+i+',\'mode\',this.value)">'
      +'<option value="inc"'+(r.mode==='inc'?' selected':'')+'>Include</option>'
      +'<option value="exc"'+(r.mode==='exc'?' selected':'')+'>Exclude</option>'
      +'</select>'
      +'<input type="text" placeholder="keyword (case-insensitive)" value="'+escHtml(r.kw)+'"'
      +' oninput="cfSet('+i+',\'kw\',this.value)">'
      +'<button class="cf-rm" onclick="removeColFilter('+i+')" title="Remove">\u00d7</button>'
      +'</div>';
  }).join('');
  updateCFToggleStyle();
}

function cfSet(i, field, val){
  colFilters[i][field] = val;
  saveColFilters();
}

function escHtml(s){
  return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
}

function updateCFToggleStyle(){
  var btn = document.getElementById('colfilter-toggle');
  var active = colFilters.filter(function(r){return r.kw.trim();}).length;
  if(active){
    btn.textContent = '\u25bc Column Filters (' + active + ' active)';
    btn.classList.add('has-rules');
  } else {
    btn.textContent = '\u25bc Column Filters';
    btn.classList.remove('has-rules');
  }
}

function toggleCFPanel(){
  var body = document.getElementById('colfilter-body');
  var btn  = document.getElementById('colfilter-toggle');
  var open = body.classList.toggle('open');
  var active = colFilters.filter(function(r){return r.kw.trim();}).length;
  var arrow = open ? '\u25b2' : '\u25bc';
  btn.textContent = arrow + ' Column Filters' + (active ? ' ('+active+' active)' : '');
  if(active) btn.classList.add('has-rules'); else btn.classList.remove('has-rules');
}

function applyColFilters(job){
  for(var i=0;i<colFilters.length;i++){
    var r = colFilters[i];
    var kw = r.kw.trim().toLowerCase();
    if(!kw) continue;
    var val = (job[r.col]||'').toLowerCase();
    if(r.mode==='inc' && !val.includes(kw)) return false;
    if(r.mode==='exc' &&  val.includes(kw)) return false;
  }
  return true;
}

// ── Render ────────────────────────────────────────────────────────────────────
let cur = [...ALL];

function evalBtns(id){
  var k = String(id), ev = evals[k] || '';
  function btn(val, cls, label){
    return '<button id="ev-'+id+'-'+val+'" class="ev '+cls+(ev===val?' active':'')+'" '
      +'onclick="setEval('+id+',\''+val+'\')" title="'+label+'">'+label+'</button>';
  }
  return '<div class="eval-cell">'
    + btn('applied', 'ev-applied', 'Applied')
    + btn('yes',     'ev-yes',     'Interested')
    + btn('viewed',  'ev-viewed',  'Viewed')
    + btn('no',      'ev-no',      'Not interested')
    + btn('ignore',  'ev-ignore',  'Hide')
    + '</div>';
}

function render(jobs){
  document.getElementById('tb').innerHTML = jobs.map(function(j){
    var notified = j.first_email_date || j.date_found;
    return '<tr id="row-'+j.id+'">'
      +'<td>'+evalBtns(j.id)+'</td>'
      +'<td><a href="'+j.url+'" target="_blank">'+j.title+'</a></td>'
      +'<td>'+j.company+'</td>'
      +'<td>'+j.location+'</td>'
      +'<td>'+badge(j.source, j.source_url)+'</td>'
      +'<td>'+notified+'</td>'
      +'<td>'+(j.work_mode||'\u2014')+'</td>'
      +'<td>'+(j.salary_range||'\u2014')+'</td>'
      +'<td>'+sbar(j.match_score)+'</td>'
      +'<td>'+j.date_found+'</td>'
      +'</tr>';
  }).join('');
  document.getElementById('cnt').textContent = jobs.length + ' of ' + ALL.length;
  updateThIndicators();
}

function doFilter(){
  var q  = document.getElementById('si').value.toLowerCase();
  var sf = document.getElementById('sf').value;
  var so = document.getElementById('so').value;
  var se = document.getElementById('se').value;

  cur = ALL.filter(function(j){
    if(q && !(j.title+' '+j.company+' '+j.location).toLowerCase().includes(q)) return false;
    if(sf && j.source !== sf) return false;
    var ev = evals[String(j.id)] || '';
    if(se === 'yes'     && ev !== 'yes')     return false;
    if(se === 'viewed'  && ev !== 'viewed')  return false;
    if(se === 'no'      && ev !== 'no')      return false;
    if(se === 'ignore'  && ev !== 'ignore')  return false;
    if(se === 'applied' && ev !== 'applied') return false;
    if(se === 'unseen'  && ev !== '')        return false;
    if(se === '' && ev === 'ignore')         return false;
    if(se === 'nothide' && ev === 'ignore')  return false;
    if(!applyColFilters(j)) return false;
    return true;
  });

  cur.sort(function(a,b){
    if(so === 'score_asc')    return a.match_score - b.match_score;
    if(so === 'date_desc')    return b.date_found.localeCompare(a.date_found);
    if(so === 'date_asc')     return a.date_found.localeCompare(b.date_found);
    if(so === 'company_asc')  return a.company.localeCompare(b.company);
    if(so === 'company_desc') return b.company.localeCompare(a.company);
    if(so === 'source_asc')   return a.source.localeCompare(b.source);
    if(so === 'source_desc')  return b.source.localeCompare(a.source);
    if(so === 'status_asc')   return evalOrder(a.id) - evalOrder(b.id);
    if(so === 'status_desc')  return evalOrder(b.id) - evalOrder(a.id);
    if(so === 'notified_desc'){
      var na=(a.first_email_date||a.date_found), nb=(b.first_email_date||b.date_found);
      return nb.localeCompare(na);
    }
    if(so === 'notified_asc'){
      var na=(a.first_email_date||a.date_found), nb=(b.first_email_date||b.date_found);
      return na.localeCompare(nb);
    }
    return b.match_score - a.match_score;
  });

  render(cur);
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadColFilters();
doFilter();
"""

SAVE_BTN_LABEL = '\U0001f4be Save Evaluations'

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
    '<select id="so" onchange="doFilter();updateThIndicators()">'
    '<option value="score_desc">Score \u2193</option>'
    '<option value="score_asc">Score \u2191</option>'
    '<option value="status_asc">Status (best first)</option>'
    '<option value="status_desc">Status (worst first)</option>'
    '<option value="date_desc">Found Date \u2193</option>'
    '<option value="date_asc">Found Date \u2191</option>'
    '<option value="notified_desc">First Notified \u2193</option>'
    '<option value="notified_asc">First Notified \u2191</option>'
    '<option value="source_asc">Source A\u2013Z</option>'
    '<option value="source_desc">Source Z\u2013A</option>'
    '<option value="company_asc">Company A\u2013Z</option>'
    '<option value="company_desc">Company Z\u2013A</option>'
    '</select>'
    '<select id="se" onchange="doFilter()">'
    '<option value="">Active (hide ignored)</option>'
    '<option value="unseen">Unseen</option>'
    '<option value="yes">\u2713 Interested</option>'
    '<option value="viewed">Viewed</option>'
    '<option value="applied">\u2192 Applied</option>'
    '<option value="no">\u2717 Not interested</option>'
    '<option value="ignore">\u2013 Ignored only</option>'
    '<option value="all_statuses">All (including ignored)</option>'
    '</select>'
    '<span class="cnt" id="cnt"></span>'
    '</div>'
    '<div id="colfilter-panel">'
    '<button id="colfilter-toggle" onclick="toggleCFPanel()">\u25bc Column Filters</button>'
    '<div id="colfilter-body">'
    '<div id="cf-rows"></div>'
    '<button id="cf-add" onclick="addColFilter()">\u002b Add Filter Rule</button>'
    '</div>'
    '</div>'
    '<div style="overflow-x:auto"><table><thead><tr>'
    '<th id="th-status"   class="sortable" onclick="thClick(\'th-status\')">Status</th>'
    '<th>Title</th>'
    '<th id="th-company"  class="sortable" onclick="thClick(\'th-company\')">Company</th>'
    '<th>Location</th>'
    '<th id="th-source"   class="sortable" onclick="thClick(\'th-source\')">Source</th>'
    '<th id="th-notified" class="sortable" onclick="thClick(\'th-notified\')">First Notified</th>'
    '<th>Mode</th><th>Salary</th>'
    '<th id="th-score"    class="sortable" onclick="thClick(\'th-score\')">Score</th>'
    '<th id="th-found"    class="sortable" onclick="thClick(\'th-found\')">Found</th>'
    '</tr></thead><tbody id="tb"></tbody></table></div>'
    '</div>'
    '<div id="savebar">'
    '<span id="saveinfo" style="color:#94a3b8;font-size:11px"></span>'
    '<button id="exportbtn" onclick="exportCSV()">Export CSV</button>'
    '<button id="savebtn" onclick="saveEvals()">' + SAVE_BTN_LABEL + '</button>'
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

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)

print("generate_dashboard: {} jobs \u2192 {} ({} KB)".format(
    len(rows), OUT, round(len(html)/1024, 1)))
print("  evaluations loaded: {} entries from {}".format(len(evaluations), EVAL))
