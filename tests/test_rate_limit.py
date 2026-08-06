import pytest

import rate_limit
from rate_limit import SlidingWindowLimiter


@pytest.fixture(autouse=True)
def clean_counters():
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()


def test_allows_up_to_the_limit():
    limiter = SlidingWindowLimiter(limit=3, window=60)
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, True]


def test_blocks_past_the_limit():
    limiter = SlidingWindowLimiter(limit=2, window=60)
    limiter.check("a")
    limiter.check("a")
    allowed, retry_after = limiter.check("a")
    assert allowed is False
    assert 0 < retry_after <= 60


def test_clients_are_tracked_separately():
    limiter = SlidingWindowLimiter(limit=1, window=60)
    assert limiter.check("a")[0] is True
    assert limiter.check("b")[0] is True
    assert limiter.check("a")[0] is False


def test_window_slides(monkeypatch):
    """A caller must not get 2x the limit by straddling a boundary."""
    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])

    limiter = SlidingWindowLimiter(limit=2, window=10)
    assert limiter.check("a")[0] is True   # t=1000
    now[0] = 1005.0
    assert limiter.check("a")[0] is True   # t=1005
    assert limiter.check("a")[0] is False  # both still in window

    now[0] = 1011.0                        # first hit has aged out
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is False  # t=1005 hit still counts


def test_retry_after_counts_down(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])

    limiter = SlidingWindowLimiter(limit=1, window=60)
    limiter.check("a")
    assert limiter.check("a")[1] == pytest.approx(60.0)
    now[0] = 30.0
    assert limiter.check("a")[1] == pytest.approx(30.0)


def test_zero_limit_disables_the_check():
    limiter = SlidingWindowLimiter(limit=0, window=60)
    assert all(limiter.check("a")[0] for _ in range(100))


def test_reset_clears_counters():
    limiter = SlidingWindowLimiter(limit=1, window=60)
    limiter.check("a")
    limiter.reset()
    assert limiter.check("a")[0] is True


def test_search_endpoint_rate_limits(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "search_limiter", SlidingWindowLimiter(limit=2, window=60))

    for _ in range(2):
        assert client.post("/api/search", json={"query": "x"}).status_code == 200

    response = client.post("/api/search", json={"query": "x"})
    assert response.status_code == 429
    assert response.is_json
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) >= 1


def test_summaries_have_a_tighter_budget(client, monkeypatch):
    """A plain search must still work after the summary budget is spent."""
    monkeypatch.setattr(rate_limit, "search_limiter", SlidingWindowLimiter(limit=100, window=60))
    monkeypatch.setattr(rate_limit, "summary_limiter", SlidingWindowLimiter(limit=1, window=60))

    import generation
    monkeypatch.setattr(generation, "summarize", lambda q, r: "overview")

    assert client.post("/api/search", json={"query": "x", "summarize": True}).status_code == 200
    assert client.post("/api/search", json={"query": "x", "summarize": True}).status_code == 429
    # Retrieval is still available.
    assert client.post("/api/search", json={"query": "x"}).status_code == 200


def test_a_rejected_search_does_not_consume_budget(client, monkeypatch):
    """Validation failures happen before the limiter, so typos are free."""
    monkeypatch.setattr(rate_limit, "search_limiter", SlidingWindowLimiter(limit=2, window=60))

    for _ in range(5):
        assert client.post("/api/search", json={"query": ""}).status_code == 400

    assert client.post("/api/search", json={"query": "x"}).status_code == 200


def test_other_endpoints_are_not_limited(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "search_limiter", SlidingWindowLimiter(limit=1, window=60))
    client.post("/api/search", json={"query": "x"})
    for _ in range(5):
        assert client.get("/api/agents").status_code == 200
        assert client.get("/api/stats").status_code == 200


def test_idle_clients_are_forgotten(monkeypatch):
    """The key table must not grow one permanent entry per address seen."""
    now = [0.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])

    limiter = SlidingWindowLimiter(limit=5, window=10)
    for i in range(50):
        limiter.check(f"client-{i}")
    assert len(limiter._hits) == 50

    now[0] = 100.0  # everything has aged out
    limiter.check("someone-new")
    assert len(limiter._hits) == 1


def test_pruning_does_not_forget_an_active_client(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])

    limiter = SlidingWindowLimiter(limit=1, window=10)
    limiter.check("busy")
    now[0] = 5.0
    limiter.check("other")
    assert limiter.check("busy")[0] is False  # still within its window
