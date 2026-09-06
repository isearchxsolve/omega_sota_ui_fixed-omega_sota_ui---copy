"""Tests for FastAPI Web UI (SSE progress)."""

import json

import pytest
from fastapi.testclient import TestClient

from omega_agent import Config
from omega_agent.ui.web_app import _sse, create_web_app


def test_sse_format():
    raw = _sse("progress", {"percent": 50, "log": "hello"})
    assert "event: progress\n" in raw
    payload = json.loads(raw.split("data: ", 1)[1].strip())
    assert payload["percent"] == 50


def test_web_app_routes():
    app = create_web_app(Config(use_mock_llm=True, log_level="ERROR"))
    client = TestClient(app)

    r = client.get("/")
    assert r.status_code == 200
    assert "OMEGA" in r.text

    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ui"] == "fastapi-sse-get"


def test_start_and_stream_events():
    app = create_web_app(Config(use_mock_llm=True, log_level="ERROR"))
    client = TestClient(app)

    start = client.post(
        "/api/chat/start",
        json={"message": "say hello in one sentence", "max_time": 120},
    )
    assert start.status_code == 200
    body = start.json()
    assert "job_id" in body
    assert "events_url" in body

    with client.stream("GET", body["events_url"]) as resp:
        assert resp.status_code == 200
        chunk = ""
        for part in resp.iter_text():
            chunk += part
            if "event: progress" in chunk and "OMEGA" in chunk:
                break
        assert "event: progress" in chunk
