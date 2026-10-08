"""Private approval UI. No downloads, imports, or deletions."""
import base64
import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from approvals import ApprovalStore

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stowarr approvals</title>
<style>body{background:#101923;color:#e4eef7;font:16px system-ui;max-width:950px;margin:40px auto;padding:0 20px}h1{margin-bottom:8px}.muted{color:#9eb2c4}article{background:#192737;border:1px solid #32475c;border-radius:14px;padding:22px;margin:18px 0}button,select{font:inherit;padding:10px 16px;border-radius:8px;border:0;margin-right:10px}button{background:#5fe3c2;color:#10241f;cursor:pointer}.reject{background:#ffb7ad}#message{white-space:pre-wrap}dt{color:#9eb2c4}dd{margin:4px 0 14px;overflow-wrap:anywhere}article:target{border-color:#5fe3c2}</style>
<h1>Stowarr approvals</h1><p class="muted">Approve staging of one exact release. Replacing or deleting the original requires a separate verified workflow.</p>
<label>Show <select id="filter"><option value="pending">Pending</option><option value="all">All requests</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="expired">Expired</option></select></label><button id="refresh">Refresh</button><p id="message" role="status"></p><main id="requests"></main>
<script>
let csrf='', items=[];const q=s=>document.querySelector(s), gib=n=>(n/1073741824).toFixed(2)+' GiB';
function node(tag,text){const e=document.createElement(tag);e.textContent=text;return e}
async function load(){try{const r=await fetch('/api/requests');if(!r.ok)throw Error('Unable to load requests');const data=await r.json();csrf=data.csrf;items=data.requests;render()}catch(e){q('#message').textContent=e.message}}
function render(){const root=q('#requests');root.replaceChildren();for(const r of items){if(q('#filter').value!=='all'&&r.status!==q('#filter').value)continue;const s=r.snapshot,a=node('article','');a.id=r.id;a.append(node('h2',s.title),node('p',r.status.toUpperCase()));const dl=node('dl','');for(const [k,v] of [['Proposed release',s.release_title],['Storage',gib(s.source_size_bytes)+' → '+gib(s.release_size_bytes)+' · save '+gib(s.source_size_bytes-s.release_size_bytes)],['Scope','Stage download only'],['Expires',new Date(r.expires_at).toLocaleString()],['Decision',r.actor? r.actor+' · '+new Date(r.decided_at).toLocaleString():'Awaiting approval']])dl.append(node('dt',k),node('dd',v));a.append(dl);if(r.status==='pending')for(const [text,decision] of [['Approve staging','approved'],['Reject','rejected']]){const b=node('button',text);if(decision==='rejected')b.className='reject';b.onclick=async()=>{b.disabled=true;try{const res=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({id:r.id,fingerprint:r.fingerprint,decision,csrf})});const data=await res.json();if(!res.ok)throw Error(data.error);q('#message').textContent='Decision recorded. The staging service will recheck and process approved requests.';await load()}catch(e){q('#message').textContent=e.message;b.disabled=false}};a.append(b)}root.append(a)}if(!root.childElementCount)root.append(node('p','No requests in this view.'))}
q('#refresh').onclick=load;q('#filter').onchange=render;if(location.hash)q('#filter').value='all';load();
</script></html>'''


def make_handler(store, username, password):
    csrf = secrets.token_urlsafe(32)
    expected = (username + ":" + password).encode()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass  # Do not log credentials, request payloads or URLs.

        def send(self, status, body, content_type="application/json"):
            if isinstance(body, dict):
                body = json.dumps(body)
            body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header("Referrer-Policy", "no-referrer")
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="Stowarr", charset="UTF-8"')
            self.end_headers()
            self.wfile.write(body)

        def authenticated(self):
            try:
                scheme, value = self.headers.get("Authorization", "").split(" ", 1)
                valid = scheme.lower() == "basic" and hmac.compare_digest(base64.b64decode(value, validate=True), expected)
            except (ValueError, TypeError):
                valid = False
            if not valid:
                self.send(401, {"error": "Authentication required"})
            return valid

        def do_GET(self):
            if not self.authenticated():
                return
            if self.path == "/":
                self.send(200, PAGE, "text/html")
            elif self.path == "/api/requests":
                self.send(200, {"csrf": csrf, "requests": store.list()})
            else:
                self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authenticated():
                return
            if self.path != "/api/decision":
                self.send(404, {"error": "Not found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096 or self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                    raise ValueError("Invalid request")
                form = parse_qs(self.rfile.read(size).decode(), strict_parsing=True)
                if set(form) != {"id", "fingerprint", "decision", "csrf"} or any(len(v) != 1 for v in form.values()):
                    raise ValueError("Invalid form")
                if not hmac.compare_digest(form["csrf"][0].encode(), csrf.encode()):
                    self.send(403, {"error": "Invalid session; refresh"})
                    return
                store.decide(form["id"][0], form["fingerprint"][0], form["decision"][0], username)
            except (ValueError, UnicodeError):
                self.send(409, {"error": "Invalid, expired, or already decided request; refresh"})
                return
            self.send(200, {"ok": True})

    return Handler


def main():
    username = os.getenv("STOWARR_APPROVAL_USER", "stowarr")
    password = os.environ.get("STOWARR_APPROVAL_PASSWORD", "")
    if not username or ":" in username or len(password) < 24:
        raise SystemExit("Set STOWARR_APPROVAL_PASSWORD to at least 24 characters and a valid username")
    store = ApprovalStore(os.getenv("STOWARR_APPROVAL_DB", "/app/data/approvals.sqlite3"))
    server = ThreadingHTTPServer(("0.0.0.0", 8787), make_handler(store, username, password))
    server.timeout = 10
    print("Stowarr approval UI listening on port 8787; media execution disabled", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
