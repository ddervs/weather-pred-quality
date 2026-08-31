"""Pin the transient-failure retry policy in wpq.fetchers._get_json.

Every source goes through this one function, and the collector's exit status is
the alerting signal — so a gap in what counts as retryable turns a blip at an
upstream API into a red run and a lost collection cycle. SEPA dropped
connections on 2026-08-15 and 2026-08-27..30 without ever returning a status
code; those went unretried and cost ~15h of Scottish rainfall.

Run: uv run pytest
"""

import pytest
import requests

from wpq import fetchers

ATTEMPTS = len(fetchers._RETRY_DELAYS) + 1


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


class FakeSession:
    """Replays a scripted sequence of responses (or exceptions to raise)."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def slept(monkeypatch):
    """Record backoff delays instead of waiting them out."""
    delays = []
    monkeypatch.setattr(fetchers.time, "sleep", delays.append)
    return delays


def run(monkeypatch, *outcomes):
    session = FakeSession(*outcomes)
    monkeypatch.setattr(fetchers, "_session", session)
    return session


def test_dropped_connection_is_retried(monkeypatch, slept):
    # the exact SEPA failure: connection closed with no response, then recovery
    session = run(monkeypatch,
                  requests.ConnectionError("Remote end closed connection without response"),
                  FakeResponse(200, {"ok": True}))
    assert fetchers._get_json("https://example.test") == {"ok": True}
    assert session.calls == 2
    assert slept == [fetchers._RETRY_DELAYS[0]]


def test_connect_timeout_is_retried(monkeypatch, slept):
    session = run(monkeypatch,
                  requests.ConnectTimeout("connect timeout=90"),
                  requests.ConnectTimeout("connect timeout=90"),
                  FakeResponse(200, [1, 2]))
    assert fetchers._get_json("https://example.test") == [1, 2]
    assert session.calls == ATTEMPTS
    assert slept == list(fetchers._RETRY_DELAYS)


def test_persistent_connection_error_still_fails_the_run(monkeypatch, slept):
    # a genuinely dead source must stay red: that is what raises the alert
    session = run(monkeypatch, *[requests.ConnectionError("down")] * ATTEMPTS)
    with pytest.raises(requests.ConnectionError):
        fetchers._get_json("https://example.test")
    assert session.calls == ATTEMPTS
    assert slept == list(fetchers._RETRY_DELAYS)


def test_retryable_status_is_retried(monkeypatch, slept):
    session = run(monkeypatch, FakeResponse(503), FakeResponse(200, {"ok": True}))
    assert fetchers._get_json("https://example.test") == {"ok": True}
    assert session.calls == 2


def test_persistent_retryable_status_raises(monkeypatch, slept):
    session = run(monkeypatch, *[FakeResponse(502)] * ATTEMPTS)
    with pytest.raises(requests.HTTPError):
        fetchers._get_json("https://example.test")
    assert session.calls == ATTEMPTS


def test_client_error_fails_fast(monkeypatch, slept):
    # 404 means the request is wrong, not the server sick - no point sleeping 35s
    session = run(monkeypatch, FakeResponse(404))
    with pytest.raises(requests.HTTPError):
        fetchers._get_json("https://example.test")
    assert session.calls == 1
    assert slept == []
