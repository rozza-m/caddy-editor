import http.server
import socketserver
import urllib.parse
import os
import subprocess
import tempfile
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="Caddyfile", help="Path to the Caddyfile to edit")
parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
parser.add_argument("--title", default="Caddyfile Editor", help="Custom title for the editor UI")
args = parser.parse_args()

CADDYFILE_PATH = os.path.abspath(args.config)
PORT = args.port

class CaddyfileHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/branding':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(args.title.encode('utf-8'))
            return

        if self.path == '/api/caddyfile':
            try:
                with open(CADDYFILE_PATH, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"") # Empty if doesn't exist yet
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/caddyfile':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')

            # Validate first using a temp file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
                tmp.write(post_data)
                tmp_path = tmp.name

            try:
                # Run caddy validate
                validate_process = subprocess.run(
                    ['caddy', 'validate', '--config', tmp_path, '--adapter', 'caddyfile'],
                    capture_output=True, text=True
                )

                if validate_process.returncode != 0:
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    err_msg = f"Validation failed:\n{validate_process.stdout}\n{validate_process.stderr}"
                    self.wfile.write(err_msg.encode('utf-8'))
                    return

                # If validation success, write to actual file
                with open(CADDYFILE_PATH, 'w', encoding='utf-8') as f:
                    f.write(post_data)

                # Run caddy reload
                reload_process = subprocess.run(
                    ['caddy', 'reload', '--config', CADDYFILE_PATH, '--adapter', 'caddyfile'],
                    capture_output=True, text=True
                )

                if reload_process.returncode != 0:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    err_msg = f"Reload failed:\n{reload_process.stdout}\n{reload_process.stderr}"
                    self.wfile.write(err_msg.encode('utf-8'))
                    return

                # Success
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                success_msg = f"Caddy reloaded successfully.\n{reload_process.stdout}\n{reload_process.stderr}"
                self.wfile.write(success_msg.encode('utf-8'))

            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        else:
            self.send_response(404)
            self.end_headers()

with socketserver.TCPServer(("", PORT), CaddyfileHandler) as httpd:
    print(f"Serving Caddyfile API on port {PORT}, editing {CADDYFILE_PATH}")
    httpd.serve_forever()
