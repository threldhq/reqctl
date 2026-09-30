import base64
import hashlib
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .baseline import _git
from .corpus import ReqctlError

PAGE = Path(__file__).resolve().parent / "portal.html"
SCRIPT = re.compile(rb"<script>(.*?)</script>", re.S)
HOST, PORT = "127.0.0.1", 8374
GITHUB = re.compile(r"(?:(?:https?|ssh|git)://(?:[^@/]+@)?|[^@/:]+@)"
                    r"(?i:github\.com)[:/]([A-Za-z0-9-]+/[A-Za-z0-9._-]+?)"
                    r"(?:\.git)?/?")
USERINFO = re.compile(r"(?<=//)[^@/]+@")


def repository(where):
    # @req+ REQ-95796962@YsAwm-tWkbqN 2v7p2v
    if _git(where, "rev-parse", "--git-dir").returncode:
        raise ReqctlError("not inside a git repository, so no origin remote "
                          "names the portal's repository")
    url = _git(where, "remote", "get-url", "origin").stdout.strip()
    if not url:
        raise ReqctlError("no origin remote names the portal's repository -- "
                          "add one naming a GitHub owner/repo")
    found = GITHUB.fullmatch(url)
    if found is None:
        raise ReqctlError(f"origin is {USERINFO.sub('', url)}, not a GitHub "
                          "owner/repo")
    # @req- 2v7p2v
    # @req> REQ-53764133@hNDAdKGPLVUD mbl5cu
    return found.group(1)


# @req> REQ-56725181@knOj5NP_RuL_ 52i7vh
def policy_of(page):
    script = base64.b64encode(hashlib.sha256(SCRIPT.search(page).group(1)).digest())
    return (f"default-src 'none'; script-src 'sha256-{script.decode()}'; "
            "style-src 'unsafe-inline'; connect-src https://api.github.com; "
            "form-action 'none'")


# @req> REQ-49576265@TZb-gviCuP5Y 6hnjpw
class Page(BaseHTTPRequestHandler):
    body = b""
    policy = ""

    def do_GET(self):
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # @req> REQ-56725181@knOj5NP_RuL_ fml6m3
        self.send_header("Content-Security-Policy", self.policy)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *_):
        pass


# @req> REQ-49576265@TZb-gviCuP5Y uor45m
def server():
    Page.body = PAGE.read_bytes()
    Page.policy = policy_of(Page.body)
    try:
        return ThreadingHTTPServer((HOST, PORT), Page)
    except OSError as busy:
        raise ReqctlError(f"cannot serve the portal at {HOST}:{PORT}: "
                          f"{busy.strerror}") from busy
