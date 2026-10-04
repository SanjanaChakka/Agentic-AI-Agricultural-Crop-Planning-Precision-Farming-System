"""Developer smoke script: exercise the live API surface and report failures.

Not part of the test suite - it exists to surface router/runtime errors quickly
while iterating.  Run with::

    python -m scripts.smoke            # in-process (TestClient)
    python -m scripts.smoke --live     # against http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
API = "/api/v1"


class Recorder:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str, str]] = []
        self.ok = 0

    def check(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        expect: int | None = None,
        binary: bool = False,
    ) -> dict | None:
        url = BASE + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - BASE is a fixed local URL
        request.add_header("Content-Type", "application/json")
        raw = b""
        try:
            with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - BASE is a fixed local URL
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            raw = exc.read()
        except Exception as exc:  # noqa: BLE001
            self.failures.append((method, path, f"transport error: {exc}"))
            return None

        if binary or "application/pdf" in content_type or not content_type.startswith(("application/json", "text/")):
            self.ok += 1
            print(f"  ok  {method:6s} {path} -> {status} ({content_type or 'binary'}, {len(raw)} bytes)")
            if status >= 400:
                self.failures.append((method, path, f"HTTP {status}: {raw[:200]!r}"))
            return None

        payload = raw.decode("utf-8", errors="replace")
        parsed: dict | list | None
        try:
            parsed = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = None

        if expect is not None:
            if status == expect:
                self.ok += 1
                print(f"  ok  {method:6s} {path} -> {status} (expected)")
                return parsed
            detail = payload[:400] if parsed is None else json.dumps(parsed)[:400]
            self.failures.append((method, path, f"expected {expect}, got {status}: {detail}"))
            return parsed
        if status >= 400:
            detail = payload[:400] if parsed is None else json.dumps(parsed)[:400]
            self.failures.append((method, path, f"HTTP {status}: {detail}"))
            return parsed
        self.ok += 1
        print(f"  ok  {method:6s} {path} -> {status}")
        return parsed  # type: ignore[return-value]


def run() -> int:
    rec = Recorder()
    print("== system ==")
    rec.check("GET", "/")
    rec.check("GET", f"{API}/health") or {}
    rec.check("GET", f"{API}/health/live")
    rec.check("GET", f"{API}/health/ready")
    rec.check("GET", f"{API}/dashboard")
    rec.check("GET", "/openapi.json")

    print("== farms & fields ==")
    farms = rec.check("GET", f"{API}/farms") or []
    farm_id = farms[0]["id"] if farms else 1
    rec.check("GET", f"{API}/farms/{farm_id}")
    rec.check("GET", f"{API}/farms/{farm_id}/summary")
    farm_detail = rec.check("GET", f"{API}/farms/{farm_id}") or {}
    fields = farm_detail.get("fields", []) if isinstance(farm_detail, dict) else []
    field_id = fields[0]["id"] if fields else 1
    crop = (fields[0].get("proposed_crop") if fields else None) or "rice"
    rec.check("GET", f"{API}/fields/{field_id}")
    rec.check("GET", f"{API}/fields/counts")

    print("== soil ==")
    latest = rec.check("GET", f"{API}/soil/fields/{field_id}/latest") or {}
    observation_id = latest.get("id") if isinstance(latest, dict) else None
    rec.check("GET", f"{API}/soil/observations?field_id={field_id}")
    rec.check("GET", f"{API}/soil/thresholds")
    if observation_id:
        rec.check("GET", f"{API}/soil/observations/{observation_id}")
        rec.check("GET", f"{API}/soil/observations/{observation_id}/evidence")

    print("== sensors ==")
    rec.check("GET", f"{API}/sensors/fields/{field_id}/latest")
    rec.check("GET", f"{API}/sensors/fields/{field_id}/trend?hours=48")
    rec.check("GET", f"{API}/sensors/fields/{field_id}/quality")
    rec.check("GET", f"{API}/sensors/readings?field_id={field_id}&limit=20")

    print("== weather ==")
    rec.check("GET", f"{API}/weather/fields/{field_id}")
    rec.check("GET", f"{API}/weather/fields/{field_id}/evidence")
    lat = (fields[0].get("effective_latitude") or fields[0].get("latitude")) if fields else None
    lon = (fields[0].get("effective_longitude") or fields[0].get("longitude")) if fields else None
    rec.check("GET", f"{API}/weather/lookup?latitude={lat or 17.38}&longitude={lon or 78.48}")

    print("== analysis (suitability / irrigation / risk / ml) ==")
    rec.check("GET", f"{API}/suitability/crops")
    rec.check("POST", f"{API}/suitability/assess?field_id={field_id}", {"crop": crop})
    rec.check("GET", f"{API}/suitability/fields/{field_id}")
    rec.check("POST", f"{API}/irrigation/assess?field_id={field_id}", {"crop": crop})
    rec.check("GET", f"{API}/irrigation/fields/{field_id}")
    rec.check("GET", f"{API}/risk/fields/{field_id}?crop={crop}")
    rec.check("GET", f"{API}/risk/fields/{field_id}/history")
    rec.check("GET", f"{API}/risk/disclaimer")
    rec.check("GET", f"{API}/ml/models")
    rec.check("GET", f"{API}/ml/status")
    rec.check("POST", f"{API}/ml/predict?field_id={field_id}", {"crop": crop})
    rec.check("GET", f"{API}/ml/fields/{field_id}/predictions")

    print("== knowledge (RAG) ==")
    rec.check("GET", f"{API}/knowledge/status")
    rec.check("GET", f"{API}/knowledge/documents")
    hits = rec.check("POST", f"{API}/knowledge/search", {"query": "ideal soil pH for rice", "top_k": 4})
    if isinstance(hits, dict) and hits.get("references"):
        rec.check("GET", f"{API}/knowledge/documents/{hits['references'][0]['doc_key']}")

    print("== workflow ==")
    rec.check("GET", f"{API}/agents")
    rec.check("GET", f"{API}/agents/graph")
    rec.check("GET", f"{API}/workflow/runs")
    run_payload = rec.check("POST", f"{API}/workflow/runs", {"field_id": field_id, "crop": crop})
    run_id = run_payload.get("id") if isinstance(run_payload, dict) else None
    if run_id:
        rec.check("GET", f"{API}/workflow/runs/{run_id}")
        rec.check("GET", f"{API}/workflow/runs/{run_id}/traces")
        rec.check("GET", f"{API}/workflow/runs/{run_id}/summary")
        rec.check("GET", f"{API}/workflow/runs/field/{field_id}/latest")

    print("== approvals, activities, alerts ==")
    rec.check("GET", f"{API}/approvals")
    rec.check("GET", f"{API}/approvals/pending")
    rec.check("GET", f"{API}/approvals/safety-contract")
    if run_id:
        rec.check("POST", f"{API}/activities/plan", {"workflow_run_id": run_id})
    rec.check("GET", f"{API}/activities")
    rec.check("GET", f"{API}/activities/fields/{field_id}/upcoming")
    rec.check("GET", f"{API}/alerts")
    rec.check("GET", f"{API}/alerts/open")
    rec.check("GET", f"{API}/alerts/dedup-policy")

    print("== reports ==")
    rec.check("GET", f"{API}/reports")
    report = None
    if run_id:
        report = rec.check("POST", f"{API}/workflow/runs/{run_id}/report", {"include_evidence": True})
    else:
        report = rec.check("POST", f"{API}/reports?field_id={field_id}", {})
    if isinstance(report, dict) and report.get("id"):
        rec.check("GET", f"{API}/reports/{report['id']}")
        rec.check("GET", f"{API}/reports/{report['id']}/download", binary=True)

    print("== error handling ==")
    rec.check("GET", f"{API}/farms/999999", expect=404)
    rec.check("POST", f"{API}/workflow/runs", {"field_id": 999999}, expect=404)

    print()
    print(f"passed: {rec.ok}   failed: {len(rec.failures)}")
    for method, path, detail in rec.failures:
        print(f"  FAIL {method} {path}\n       {detail}")
    return 1 if rec.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="target a running uvicorn")
    args = parser.parse_args()
    if args.live:
        return run()

    from fastapi.testclient import TestClient

    from app.main import app

    failures: list[tuple[str, str, str]] = []
    # Endpoints with mandatory query parameters that are not exercised by the
    # generic sweep (they are covered by the --live pass with real values).
    required_params = {
        "/api/v1/weather/lookup": {"latitude": "17.38", "longitude": "78.48"},
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        for route in app.routes:
            if not getattr(route, "path", "").startswith(API):
                continue
            methods = getattr(route, "methods", set())
            if "GET" in methods and "{" not in route.path:
                response = client.get(route.path, params=required_params.get(route.path, {}))
                status = "ok" if response.status_code < 400 else "FAIL"
                if status == "FAIL":
                    failures.append(("GET", route.path, str(response.status_code) + " " + response.text[:200]))
                print(f"  {status:4s} GET {route.path} -> {response.status_code}")
    print()
    print(f"failed: {len(failures)}")
    for method, path, detail in failures:
        print(f"  FAIL {method} {path}: {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
