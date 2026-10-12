"""Synthetic local Writer QA: no user documents, cloud calls or model downloads."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

MODEL = "Windows-Music-Lab-Writer"
SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string"}, "style": {"type": "string"},
    "lyrics": {"type": "string"}, "notes": {"type": "string"}},
    "required": ["title", "style", "lyrics", "notes"], "additionalProperties": False}
MESSAGES = [
    {"role": "system", "content": "You are a local songwriting assistant. Answer in Russian. Return a JSON object with title, style, lyrics, notes. Write four short original lyric lines about a fictional paper boat. Never use tools."},
    {"role": "user", "content": "Придумай название, спокойный акустический стиль и четыре короткие строки про бумажный кораблик. В notes напиши одно короткое предложение."}
]
BODY = {"model": MODEL, "messages": MESSAGES, "max_tokens": 256, "stream": False,
        "temperature": 0.2, "response_format": {"type": "json_schema", "json_schema":
        {"name": "brief", "schema": SCHEMA}}}

def request(path, body=None, method=None, headers=None, timeout=180):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf8")
    req = urllib.request.Request("http://127.0.0.1:41872" + path, data=data,
        method=method, headers={"Content-Type": "application/json", **(headers or {})})
    start = time.monotonic()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as response:
        content = response.read(4 * 1024 * 1024)
        return response.status, dict(response.headers), content, time.monotonic() - start

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = cli.parse_args()
    root = args.root.resolve()
    output = root / "windows/state/writer/http-check.json"
    report = {"schema_version": 1, "synthetic_only": True, "tested_at": time.time(), "checks": {}}
    status, _, raw, _ = request("/health")
    assert status == 200 and json.loads(raw)["status"] == "ok"
    report["checks"]["health"] = True
    status, _, raw, _ = request("/v1/models")
    models = json.loads(raw)["data"]
    assert status == 200 and any(item["id"] == MODEL for item in models)
    report["checks"]["openai_model_alias"] = True
    for origin in ("http://localhost:41868", "http://127.0.0.1:41868"):
        status, headers, _, _ = request("/v1/chat/completions", method="OPTIONS", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        lowered = {k.lower(): v for k, v in headers.items()}
        assert status in (200, 204), status
        assert lowered.get("access-control-allow-origin") == origin, lowered
        assert "POST" in lowered.get("access-control-allow-methods", ""), lowered
        assert "content-type" in lowered.get("access-control-allow-headers", "").lower(), lowered
    report["checks"]["cors_preflight_two_origins"] = True
    for denied in ("https://synthetic-untrusted.invalid", "http://localhost.synthetic.invalid:41868", "http://127.0.0.1.synthetic.invalid:41868"):
        status, denied_headers, _, _ = request("/v1/models", headers={"Origin": denied})
        denied_origin = {k.lower(): v for k, v in denied_headers.items()}.get("access-control-allow-origin")
        assert denied_origin not in ("*", denied), denied_headers
    report["checks"]["untrusted_origin_not_granted"] = True
    status, headers, raw, elapsed = request("/v1/chat/completions", BODY,
        headers={"Origin": "http://localhost:41868"})
    response = json.loads(raw)
    assert status == 200
    assert {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin") == "http://localhost:41868"
    result = json.loads(response["choices"][0]["message"]["content"])
    assert set(result) == set(SCHEMA["properties"])
    assert all(isinstance(result[k], str) and result[k].strip() for k in result)
    assert any("а" <= c.lower() <= "я" for c in result["lyrics"]), result
    assert len([line for line in result["lyrics"].splitlines() if line.strip()]) == 4, result
    report["checks"]["writer_json_schema_and_russian_lyrics"] = True
    report.update(response=response, writer_document=result, elapsed_seconds=elapsed,
                  max_tokens_requested=256, request_body=BODY, passed=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf8"))
    print(json.dumps({"passed": True, "elapsed_seconds": elapsed, "output": str(output)}))

if __name__ == "__main__":
    main()
