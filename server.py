import http.server
import socketserver
import urllib.parse
import os
import subprocess
import tempfile
import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="Caddyfile", help="Path to the Caddyfile to edit")
parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
parser.add_argument("--title", default="Caddyfile Editor", help="Custom title for the editor UI")
args = parser.parse_args()

CADDYFILE_PATH = os.path.abspath(args.config)
PORT = args.port

def log_api(msg):
    print(f"[API] {msg}", flush=True)

class CaddyfileHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/branding':
            log_api(f"Serving branding: {args.title}")
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(args.title.encode('utf-8'))
            return

        if self.path == '/api/caddyfile':
            try:
                log_api(f"Reading Caddyfile: {CADDYFILE_PATH}")
                with open(CADDYFILE_PATH, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except Exception as e:
                log_api(f"Error reading Caddyfile: {str(e)}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error reading file: {str(e)}".encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/caddyfile':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')

            log_api("Received save request. Validating...")

            # Validate first using a temp file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix=".caddyfile") as tmp:
                tmp.write(post_data)
                tmp_path = tmp.name

            try:
                # Run caddy validate
                log_api(f"Running: caddy validate --config {tmp_path} --adapter caddyfile")
                validate_process = subprocess.run(
                    ['caddy', 'validate', '--config', tmp_path, '--adapter', 'caddyfile'],
                    capture_output=True, text=True
                )

                if validate_process.returncode != 0:
                    out = validate_process.stdout or ""
                    err = validate_process.stderr or ""
                    log_api(f"Validation FAILED (code {validate_process.returncode})")
                    log_api(f"STDOUT: {out}")
                    log_api(f"STDERR: {err}")
                    
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    err_msg = f"Validation failed (exit {validate_process.returncode}):\n{out}\n{err}"
                    self.wfile.write(err_msg.encode('utf-8'))
                    return

                # If validation success, write to actual file
                log_api(f"Validation success. Writing to {CADDYFILE_PATH}")
                with open(CADDYFILE_PATH, 'w', encoding='utf-8') as f:
                    f.write(post_data)

                # Run caddy reload
                log_api(f"Running: caddy reload --config {CADDYFILE_PATH} --adapter caddyfile")
                reload_process = subprocess.run(
                    ['caddy', 'reload', '--config', CADDYFILE_PATH, '--adapter', 'caddyfile'],
                    capture_output=True, text=True
                )

                if reload_process.returncode != 0:
                    out = reload_process.stdout or ""
                    err = reload_process.stderr or ""
                    log_api(f"Reload FAILED (code {reload_process.returncode})")
                    log_api(f"STDOUT: {out}")
                    log_api(f"STDERR: {err}")

                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    err_msg = f"Reload failed (exit {reload_process.returncode}):\n{out}\n{err}"
                    self.wfile.write(err_msg.encode('utf-8'))
                    return

                # Success
                log_api("Caddy reloaded successfully")
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                success_msg = f"Caddy reloaded successfully.\n{reload_process.stdout}\n{reload_process.stderr}"
                self.wfile.write(success_msg.encode('utf-8'))

            except Exception as e:
                log_api(f"Internal Server Error: {str(e)}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Backend Error: {str(e)}".encode('utf-8'))
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        else:
            self.send_response(404)
            self.end_headers()

# Find caddy path to help diagnostics
try:
    caddy_path = subprocess.check_output(['which', 'caddy'], text=True).strip()
    log_api(f"Caddy binary found at: {caddy_path}")
except:
    log_api("Warning: 'caddy' not found in PATH via 'which'. subprocess calls might fail.")

with socketserver.TCPServer(("", PORT), CaddyfileHandler) as httpd:
    log_api(f"Serving Caddyfile API on port {PORT}, editing {CADDYFILE_PATH}")
    httpd.serve_forever()
