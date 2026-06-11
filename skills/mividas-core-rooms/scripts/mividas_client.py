#!/usr/bin/env python3
"""
mividas_client.py — stdlib-only Python client for the Mividas Core + Rooms API.

No external dependencies. Handles:

- HTTP Basic Auth with the admin user / service account.
- The `X-Mividas-Customer: <id>` multi-tenant header.
- The two list-shape variants this API uses
  (DRF `{count, next, previous, results}` vs bare JSON array).
- A polling helper for the endpoint provisioning task queue.

Usage:
    from mividas_client import MividasClient

    c = MividasClient("https://mividas.example.com", user, password, customer_id=7)
    customers = c.list("/customer/")
    alerts    = c.list("/monitor_endpoint/", params={"is_active": True})

    provision = c.post("/endpoint/provision/", {
        "endpoints": [1, 2, 3],
        "configuration": [{"key": ["SystemUnit", "Notifications", "Mode"], "value": "On"}],
    })
    tasks = c.wait_for_tasks(provision["id"])
"""
from __future__ import annotations

import base64
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable


class MividasError(RuntimeError):
    """Mividas API returned a non-2xx response."""

    def __init__(self, status: int, body: Any, message: str = ""):
        super().__init__(message or f"HTTP {status}")
        self.status = status
        self.body = body


class MividasClient:
    """Minimal Mividas Core + Rooms REST client."""

    # EndpointTask.status terminal values: ERROR, CANCELLED, COMPLETED
    TASK_TERMINAL_STATES = {-10, -1, 10}

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        customer_id: int | None = None,
        verify_tls: bool = True,
        timeout: float = 30.0,
    ):
        # Normalise host to "https://example.com" — strip trailing slash
        host = host.rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = "https://" + host
        self.base = host + "/json-api/v1"

        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._basic_auth = f"Basic {token}"
        self._customer_id = customer_id
        self._timeout = timeout

        if verify_tls:
            self._tls_ctx: ssl.SSLContext | None = None
        else:
            self._tls_ctx = ssl.create_default_context()
            self._tls_ctx.check_hostname = False
            self._tls_ctx.verify_mode = ssl.CERT_NONE

    # ----- core HTTP --------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        customer_id: int | None = None,
    ) -> Any:
        url = self._build_url(path, params)

        data: bytes | None = None
        headers = {
            "Authorization": self._basic_auth,
            "Accept": "application/json",
        }
        cust = customer_id if customer_id is not None else self._customer_id
        if cust is not None:
            headers["X-Mividas-Customer"] = str(cust)

        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout, context=self._tls_ctx) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = raw.decode("utf-8", errors="replace") if raw else None
            raise MividasError(e.code, body, f"{method} {path} → HTTP {e.code}") from e

    def _build_url(self, path: str, params: dict | None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            # absolute URL (e.g. a `next` pagination link)
            url = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = self.base + path

        if params:
            # Flatten lists into repeated key=value pairs (DRF convention).
            flat: list[tuple[str, str]] = []
            for k, v in params.items():
                if v is None:
                    continue
                if isinstance(v, bool):
                    flat.append((k, "true" if v else "false"))
                elif isinstance(v, (list, tuple, set)):
                    for item in v:
                        flat.append((k, str(item)))
                else:
                    flat.append((k, str(v)))
            sep = "&" if "?" in url else "?"
            url = url + sep + urllib.parse.urlencode(flat)
        return url

    # ----- convenience verbs ------------------------------------------------

    def get(self, path: str, params: dict | None = None, **kw) -> Any:
        return self._request("GET", path, params=params, **kw)

    def post(self, path: str, body: Any = None, **kw) -> Any:
        return self._request("POST", path, json_body=body or {}, **kw)

    def put(self, path: str, body: Any = None, **kw) -> Any:
        return self._request("PUT", path, json_body=body or {}, **kw)

    def patch(self, path: str, body: Any = None, **kw) -> Any:
        return self._request("PATCH", path, json_body=body or {}, **kw)

    def delete(self, path: str, body: Any = None, **kw) -> Any:
        return self._request("DELETE", path, json_body=body, **kw)

    # ----- list helpers -----------------------------------------------------

    def list(self, path: str, params: dict | None = None, **kw) -> list[Any]:
        """
        Fetch one "list" endpoint and return its items.

        Handles both shapes the API uses:
          - bare JSON array → return as-is
          - `{count, next, previous, results}` paginated dict → return `results`
            and follow `next` until exhausted (auto-pagination).
        """
        body = self.get(path, params=params, **kw)

        if isinstance(body, list):
            return body

        if not isinstance(body, dict):
            raise MividasError(200, body, f"unexpected list shape from {path}: {type(body).__name__}")

        items = list(body.get("results", []))
        next_url = body.get("next")
        while next_url:
            page = self.get(next_url)
            if not isinstance(page, dict):
                break
            items.extend(page.get("results", []))
            next_url = page.get("next")
        return items

    def iter_list(self, path: str, params: dict | None = None, **kw) -> Iterable[Any]:
        """Generator variant — yields items one page at a time without buffering."""
        body = self.get(path, params=params, **kw)
        if isinstance(body, list):
            yield from body
            return
        if not isinstance(body, dict):
            return
        yield from body.get("results", [])
        next_url = body.get("next")
        while next_url:
            page = self.get(next_url)
            if not isinstance(page, dict):
                break
            yield from page.get("results", [])
            next_url = page.get("next")

    # ----- endpoint provisioning task poller --------------------------------

    def wait_for_tasks(
        self,
        provision_id: int,
        *,
        poll_interval: float = 2.0,
        timeout: float | None = 600.0,
    ) -> list[dict]:
        """
        Poll /endpointtask/?provision=<id> until every task reaches a terminal state.

        Returns the final task list. Terminal states are ERROR (-10), CANCELLED (-1),
        and COMPLETED (10). Set `timeout=None` to wait indefinitely.
        """
        deadline = None if timeout is None else time.time() + timeout
        while True:
            tasks = self.list("/endpointtask/", params={"provision": provision_id})
            if all(t.get("status") in self.TASK_TERMINAL_STATES for t in tasks):
                return tasks
            if deadline is not None and time.time() > deadline:
                pending = [t for t in tasks if t.get("status") not in self.TASK_TERMINAL_STATES]
                raise TimeoutError(
                    f"wait_for_tasks(provision={provision_id}) timed out with "
                    f"{len(pending)} pending task(s)"
                )
            time.sleep(poll_interval)


# ---------- CLI smoke test ---------------------------------------------------

def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Smoke-test the Mividas client.")
    parser.add_argument("--host", default=os.environ.get("MIVIDAS_HOST"))
    parser.add_argument("--user", default=os.environ.get("MIVIDAS_USER"))
    parser.add_argument("--password", default=os.environ.get("MIVIDAS_PASS"))
    parser.add_argument("--customer", type=int, default=os.environ.get("MIVIDAS_CUSTOMER"))
    parser.add_argument("--no-verify", action="store_true", help="Disable TLS verification.")
    parser.add_argument(
        "--cmd",
        default="customers",
        choices=["customers", "clusters", "providers", "endpoints", "calls"],
        help="Which smoke read to run.",
    )
    args = parser.parse_args(argv)

    if not args.host or not args.user or not args.password:
        parser.error("--host / --user / --password (or MIVIDAS_HOST / MIVIDAS_USER / MIVIDAS_PASS env) required")

    c = MividasClient(
        args.host,
        args.user,
        args.password,
        customer_id=args.customer,
        verify_tls=not args.no_verify,
    )

    if args.cmd == "customers":
        for row in c.list("/customer/"):
            print(f"  [{row['id']:>3}] {row['title']}  (active={row.get('is_active')})")
    elif args.cmd == "clusters":
        for row in c.list("/cluster/"):
            print(f"  [{row['id']:>3}] {row['title']}  type={row.get('type')}")
    elif args.cmd == "providers":
        for row in c.list("/provider/"):
            print(f"  [{row['id']:>3}] {row['title']}  subtype={row.get('subtype')}  online={row.get('is_online')}")
    elif args.cmd == "endpoints":
        for row in c.list("/endpoint/"):
            print(f"  [{row['id']:>4}] {row['title']:<40}  {row.get('product_name', '')}  status={row.get('status_code')}")
    elif args.cmd == "calls":
        for row in c.list("/calls/"):
            print(f"  {row['id']}  cospace={row.get('cospace')!r}  legs={len(row.get('legs', []))}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
