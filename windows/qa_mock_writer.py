"""Owned loopback OpenAI-compatible mock. No model imports or external calls."""
import argparse
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=41872)
parser.add_argument('--cache', required=True)
args = parser.parse_args()
cache = Path(args.cache)
cache.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()
model = 'Windows-Music-Lab-Writer'
draft = {'title': 'QA Mock Draft', 'style': 'gentle piano, calm synthetic verse',
         'style_tags': 'piano, calm, acoustic',
         'lyrics': '[Verse]\nAn owned test line is here\nA second line stays clear\n[Chorus]\nThe mock returns a draft\nNo model made this craft',
         'notes': 'Synthetic mock response for UI validation; no model inference.'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def allowed_origin(self):
        origin = self.headers.get('Origin', '')
        return origin if origin in ('http://localhost:41868', 'http://127.0.0.1:41868') else ''
    def reply(self, code, value=None):
        data = json.dumps(value or {}, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        if self.allowed_origin():
            self.send_header('Access-Control-Allow-Origin', self.allowed_origin())
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def guard(self):
        return self.client_address[0] == '127.0.0.1' and self.headers.get('Host') in (f'127.0.0.1:{args.port}', f'localhost:{args.port}') and (not self.headers.get('Origin') or bool(self.allowed_origin()))
    def do_OPTIONS(self):
        self.reply(200 if self.guard() else 403)
    def do_GET(self):
        if not self.guard():
            return self.reply(403)
        if self.path == '/health':
            return self.reply(200, {'status': 'ok', 'mock_ai': True})
        if self.path in ('/v1/models', '/models'):
            return self.reply(200, {'object': 'list', 'data': [{'id': model, 'object': 'model', 'owned_by': 'owned-mock'}]})
        self.reply(404)
    def do_POST(self):
        if not self.guard() or self.path not in ('/v1/chat/completions', '/chat/completions'):
            return self.reply(403)
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 2*2**20:
            return self.reply(413)
        body = json.loads(self.rfile.read(size).decode('utf-8'))
        assert body.get('stream') is False
        with lock, (cache / 'mock-requests.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'path': self.path, 'mock_ai': True, 'body': body}, ensure_ascii=False)+'\n')
        response = {'id': 'owned-mock-completion', 'object': 'chat.completion', 'model': model,
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(draft, ensure_ascii=False)}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}, 'mock_ai': True}
        self.reply(200, response)

ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
