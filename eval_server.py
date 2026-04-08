#!/usr/bin/env python3
"""
eval_server.py  —  Tiny local HTTP server that lets job_dashboard.html
                   save evaluations back to job_evaluations.json on disk.

Run once (keep running while you use the dashboard):
    python3 ~/Documents/claude_jobhunt/eval_server.py

Listens on http://localhost:7432
  GET  /evals        → returns current job_evaluations.json
  POST /evals        → writes body JSON to job_evaluations.json
  GET  /health       → returns {"ok":true}

The dashboard calls these automatically when you click status buttons.
Stop with Ctrl-C.
"""
import http.server, json, os, sys

DIR  = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.join(DIR, 'job_evaluations.json')
PORT = 7432

class Handler(http.server.BaseHTTPRequestHandler):

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self._json(200, {'ok': True})
        elif self.path == '/evals':
            try:
                with open(EVAL) as f:
                    data = f.read()
            except FileNotFoundError:
                data = '{}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(data.encode())
        else:
            self._json(404, {'error': 'not found'})

    def do_POST(self):
        if self.path == '/evals':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                parsed = json.loads(body)
                with open(EVAL, 'w') as f:
                    json.dump(parsed, f, indent=2)
                self._json(200, {'ok': True, 'entries': len(parsed)})
                print(f"  saved {len(parsed)} evaluations → {EVAL}")
            except Exception as e:
                self._json(400, {'error': str(e)})
        else:
            self._json(404, {'error': 'not found'})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', PORT), Handler)
    print(f"eval_server: listening on http://localhost:{PORT}")
    print(f"  evaluations file: {EVAL}")
    print(f"  stop with Ctrl-C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\neval_server: stopped.")
        sys.exit(0)
