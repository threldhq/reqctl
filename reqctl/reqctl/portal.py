import base64
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import fields as _fields
from . import write as _write
from .baseline import _git
from .corpus import ReqctlError

PAGE = Path(__file__).resolve().parent / "portal.html"
SCRIPT = re.compile(rb"<script>(.*?)</script>", re.S)
FIELDS_AT = b'<script type="application/json" id="kind-fields">'
UNSAFE = {ord(char): f"\\u{ord(char):04x}" for char in "<>&"}
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


# @req+ REQ-87847146@zR5tHnA8xAWx avcfk3
# @req> REQ-69283350@XSe9n-OwepOP cgzp5c
# @req> REQ-14679866@V0QsDEPmgOq3 357tly
def _offered(kind, field):
    once = kind == "parameter" and field.name == _fields.ENTRIES
    return {"name": field.name, "flag": field.flag[2:], "required": field.required,
            "repeated": field.repeated and not once, "prose": field.prose,
            "choices": list(field.choices), "parts": list(field.parts),
            "clears": field.clears and field.clears[2:],
            "drops": field.drops and field.drops[2:],
            "form": _write.FORMS.get(field.name)}


# @req> REQ-21522236@FSo8K6fhdHTu vldi2d
def forms(root):
    offered = {}
    for kind in _write.KINDS:
        own = _fields.of(root, kind)
        offered[kind] = {"new": [_offered(kind, field) for field in own],
                         "revise": [_offered(kind, field) for field
                                    in _write.revisable_fields(own, kind)
                                    if not field.address]}
    return offered


def with_forms(page, root):
    before, after = page.split(FIELDS_AT)
    return before + FIELDS_AT + json.dumps(forms(root)).translate(UNSAFE).encode() + after
# @req- avcfk3


# @req> REQ-56725181@knOj5NP_RuL_ 52i7vh
def policy_of(page):
    script = SCRIPT.search(page).group(1).replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    held = base64.b64encode(hashlib.sha256(script).digest())
    return (f"default-src 'none'; script-src 'sha256-{held.decode()}'; "
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
    Page.body = with_forms(PAGE.read_bytes(), _fields.root())
    Page.policy = policy_of(Page.body)
    try:
        return ThreadingHTTPServer((HOST, PORT), Page)
    except OSError as busy:
        raise ReqctlError(f"cannot serve the portal at {HOST}:{PORT}: "
                          f"{busy.strerror}") from busy
