"""End-to-end tests for the HTTP API."""

import pytest

from app.shortcode import ALPHABET
from app.config import get_settings

settings = get_settings()

LONG_URL = "https://www.example.com/a/fairly/long/path?utm_source=test&ref=abc"


async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_shorten_creates_a_code(client):
    response = await client.post("/shorten", json={"url": LONG_URL})

    assert response.status_code == 201
    body = response.json()
    assert body["original_url"] == LONG_URL
    assert body["visit_count"] == 0
    assert len(body["short_code"]) == settings.short_code_length
    assert set(body["short_code"]) <= set(ALPHABET)
    assert body["short_url"].endswith(body["short_code"])


async def test_shorten_is_idempotent_for_the_same_url(client):
    first = await client.post("/shorten", json={"url": LONG_URL})
    second = await client.post("/shorten", json={"url": LONG_URL})

    assert first.json()["short_code"] == second.json()["short_code"]


async def test_shorten_gives_distinct_codes_to_distinct_urls(client):
    first = await client.post("/shorten", json={"url": "https://example.com/one"})
    second = await client.post("/shorten", json={"url": "https://example.com/two"})

    assert first.json()["short_code"] != second.json()["short_code"]


@pytest.mark.parametrize(
    "bad_url",
    [
        "not-a-url",
        "example.com",           # no scheme
        "ftp://example.com",     # unsupported scheme
        "",
    ],
)
async def test_shorten_rejects_invalid_urls(client, bad_url):
    response = await client.post("/shorten", json={"url": bad_url})
    assert response.status_code == 422


async def test_shorten_rejects_a_missing_body(client):
    response = await client.post("/shorten", json={})
    assert response.status_code == 422


async def test_redirect_points_at_the_original_url(client):
    short_code = (await client.post("/shorten", json={"url": LONG_URL})).json()[
        "short_code"
    ]

    response = await client.get(f"/{short_code}")

    assert response.status_code == 307
    assert response.headers["location"] == LONG_URL


async def test_redirect_increments_the_visit_count(client):
    short_code = (await client.post("/shorten", json={"url": LONG_URL})).json()[
        "short_code"
    ]

    for _ in range(3):
        await client.get(f"/{short_code}")

    stats = await client.get(f"/stats/{short_code}")
    assert stats.json()["visit_count"] == 3
    assert stats.json()["last_visited_at"] is not None


async def test_unknown_code_returns_404(client):
    response = await client.get("/aBc1234")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


async def test_code_outside_the_alphabet_returns_404(client):
    response = await client.get("/not-a-code!")
    assert response.status_code == 404


async def test_stats_does_not_count_as_a_visit(client):
    short_code = (await client.post("/shorten", json={"url": LONG_URL})).json()[
        "short_code"
    ]

    await client.get(f"/stats/{short_code}")
    stats = await client.get(f"/stats/{short_code}")

    assert stats.json()["visit_count"] == 0


async def test_stats_for_unknown_code_returns_404(client):
    response = await client.get("/stats/zzzzzzz")
    assert response.status_code == 404
