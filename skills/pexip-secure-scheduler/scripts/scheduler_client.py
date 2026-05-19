#!/usr/bin/env python3
"""
scheduler_client.py — a minimal, stdlib-only client for the Pexip Secure
Scheduler Portal API (v5.x).

Demonstrates the four-step encounter creation recipe from SKILL.md plus
auth + email send. Intended as a reference implementation and a CLI you
can `python scheduler_client.py demo` against a sandbox.

Stdlib only — runs anywhere Python 3.8+ is available.

Usage:
    # Show the long-lived-token bootstrap (uses basic auth to provision a
    # token; verifies which header your version surfaces the token in).
    BASE=https://scheduler.example.com USER=admin PASS=hunter2 \\
        python scheduler_client.py probe-token

    # Run the full demo: roles → alias_template → participants → encounter
    # → send_email. Idempotent-ish: looks for existing rows by name first.
    BASE=https://scheduler.example.com TOKEN=<token> \\
        python scheduler_client.py demo

    # CRUD primitives
    BASE=... TOKEN=... python scheduler_client.py list encounter
    BASE=... TOKEN=... python scheduler_client.py get encounter <uuid>
    BASE=... TOKEN=... python scheduler_client.py delete encounter <uuid>

Configuration via environment variables:
    BASE        Scheduler base URL (e.g. https://scheduler.example.com)
    TOKEN       Long-lived token (for non-token-bootstrap commands)
    USER, PASS  Basic-auth credentials (for probe-token only)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SchedulerClient:
    """Thin wrapper around the Portal API. Stdlib HTTP, no third-party deps."""

    def __init__(self, base: str, token: str | None = None, basic: tuple[str, str] | None = None):
        self.base = base.rstrip("/")
        self.token = token
        self.basic = basic

    def _headers(self, use_basic: bool = False) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if use_basic and self.basic:
            b64 = base64.b64encode(f"{self.basic[0]}:{self.basic[1]}".encode()).decode()
            h["Authorization"] = f"Basic {b64}"
        elif self.token:
            h["Authorization"] = f"Bearer {self.token}"
        elif self.basic:
            b64 = base64.b64encode(f"{self.basic[0]}:{self.basic[1]}".encode()).decode()
            h["Authorization"] = f"Basic {b64}"
        return h

    def request(self, method: str, path: str, body: Any = None, *, use_basic: bool = False,
                want_response_headers: bool = False) -> Any:
        url = self.base + path
        data = None
        headers = self._headers(use_basic=use_basic)
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                if want_response_headers:
                    return dict(resp.headers), raw
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            raise SystemExit(f"HTTP {e.code} on {method} {path}\n{err_body}") from None

    # ---- Generic CRUD ----

    def list(self, resource: str, **params) -> dict:
        q = "?" + urllib.parse.urlencode(params) if params else ""
        return self.request("GET", f"/api/{resource}/{q}")

    def list_all(self, resource: str, **params) -> list[dict]:
        """Page through a list endpoint, returning every row."""
        out: list[dict] = []
        url: str | None = "/api/" + resource + "/"
        first_q = "?" + urllib.parse.urlencode({**params, "limit": 100}) if params or True else ""
        url = url + first_q
        while url:
            page = self.request("GET", url)
            out.extend(page.get("results", []))
            next_url = page.get("next")
            # next is a fully qualified URL; strip the host to reuse our request method
            url = next_url[len(self.base):] if next_url and next_url.startswith(self.base) else next_url
            if not url:
                break
        return out

    def get(self, resource: str, id_: Any) -> dict:
        return self.request("GET", f"/api/{resource}/{id_}/")

    def create(self, resource: str, body: dict) -> dict:
        return self.request("POST", f"/api/{resource}/", body)

    def patch(self, resource: str, id_: Any, body: dict) -> dict:
        return self.request("PATCH", f"/api/{resource}/{id_}/", body)

    def delete(self, resource: str, id_: Any) -> None:
        self.request("DELETE", f"/api/{resource}/{id_}/")

    # ---- Helpers ----

    def find_by_name(self, resource: str, name: str, name_field: str = "name") -> dict | None:
        """Look up a resource by its name field. Used for idempotency in the demo."""
        for row in self.list_all(resource):
            if row.get(name_field) == name:
                return row
        return None

    def ensure_role(self, name: str, host: bool, interpreter: bool = False) -> dict:
        existing = self.find_by_name("role", name)
        if existing:
            return existing
        return self.create("role", {"name": name, "host": host, "interpreter": interpreter})

    def ensure_alias_template(self, template: str) -> dict:
        existing = self.find_by_name("alias_template", template, name_field="template")
        if existing:
            return existing
        return self.create("alias_template", {
            "template": template,
            "alias_protocols": ["SIP", "H323", "WEB"],
        })

    def ensure_participant(self, display_name: str, email: str, *, pin: str | None = None) -> dict:
        # Participants don't have a uniqueness constraint on email; we
        # treat (display_name, email) as the natural key for the demo.
        for row in self.list_all("participant"):
            if row.get("display_name") == display_name and row.get("email") == email:
                return row
        body: dict = {
            "display_name": display_name,
            "email": email,
            "authentication_method": "PIN" if pin else "",
        }
        if pin:
            body["pin"] = pin
        return self.create("participant", body)

    # ---- Token bootstrap probe ----

    def probe_token(self) -> dict:
        """Hit /api/command/long_lived_token/ with basicAuth and report which
        response header carries the token. The OpenAPI spec declares the
        response as 'no body', so the token must be in a header — but which
        header varies between versions."""
        if not self.basic:
            raise SystemExit("probe-token requires USER and PASS env vars")
        headers, _ = self.request(
            "POST", "/api/command/long_lived_token/",
            use_basic=True, want_response_headers=True,
        )
        # Reasonable candidates seen in the wild:
        candidates = [k for k in headers if k.lower() in {
            "x-token", "x-auth-token", "authorization", "x-api-token", "set-cookie",
        }]
        return {
            "response_headers": headers,
            "token_carrying_header_candidates": candidates,
        }


# ---- Demo: the four-step recipe ----

def demo(client: SchedulerClient) -> None:
    print("[1/4] Ensuring roles...")
    chair = client.ensure_role("Chair", host=True)
    guest = client.ensure_role("Guest", host=False)
    print(f"        Chair id={chair['id']}, Guest id={guest['id']}")

    print("[2/4] Ensuring alias template...")
    tmpl = client.ensure_alias_template(
        "meet.{{ participant.long_alias }}@scheduler.example.com"
    )
    print(f"        AliasTemplate id={tmpl['id']}")

    print("[3/4] Ensuring participants...")
    alice = client.ensure_participant("Alice Demo", "alice@example.com", pin="74291834")
    bob = client.ensure_participant("Bob Demo", "bob@example.com", pin="91827364")
    print(f"        Alice id={alice['id']}, Bob id={bob['id']}")

    print("[4/4] Creating encounter with nested participants...")
    encounter = client.create("encounter", {
        "name": "Demo Encounter",
        "vmr": "demo-encounter",
        "description": "Created by scheduler_client.py demo",
        "start_date": "2026-06-01",
        "start_time": "10:00:00",
        "end_time": "10:30:00",
        "timezone": "UTC",
        "enable_chat": True,
        "encounter_participants": [
            {"participant": alice["id"], "role": chair["id"]},
            {"participant": bob["id"],   "role": guest["id"]},
        ],
    })
    print(f"        Encounter id={encounter['id']}")
    print(f"        encounter_aliases={encounter.get('encounter_aliases', [])}")
    for ep in encounter.get("encounter_participants", []):
        print(f"        EP {ep['id']}: participant={ep['participant']} "
              f"role={ep['role']} aliases={ep['participant_aliases']}")

    print()
    print("Done. Run send_email to invite participants, e.g.:")
    print(f'  curl -X POST $BASE/api/command/send_email '
          f'-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" '
          f'-d \'{{"encounter":"{encounter["id"]}","participant":{alice["id"]}}}\'')


# ---- CLI ----

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1

    base = os.environ.get("BASE")
    if not base:
        print("Set BASE=https://scheduler.example.com", file=sys.stderr)
        return 2

    cmd = argv[1]

    if cmd == "probe-token":
        user, pw = os.environ.get("USER"), os.environ.get("PASS")
        if not user or not pw:
            print("probe-token requires USER and PASS env vars", file=sys.stderr)
            return 2
        client = SchedulerClient(base, basic=(user, pw))
        result = client.probe_token()
        print(json.dumps(result, indent=2))
        return 0

    token = os.environ.get("TOKEN")
    if not token:
        print("Set TOKEN=<long-lived token>", file=sys.stderr)
        return 2
    client = SchedulerClient(base, token=token)

    if cmd == "demo":
        demo(client)
        return 0

    if cmd == "list" and len(argv) >= 3:
        resource = argv[2]
        page = client.list(resource, limit=20)
        print(json.dumps(page, indent=2))
        return 0

    if cmd == "get" and len(argv) >= 4:
        resource, id_ = argv[2], argv[3]
        print(json.dumps(client.get(resource, id_), indent=2))
        return 0

    if cmd == "delete" and len(argv) >= 4:
        resource, id_ = argv[2], argv[3]
        client.delete(resource, id_)
        print(f"Deleted /api/{resource}/{id_}/")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
