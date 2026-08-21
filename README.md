# URL Shortener API

A small URL shortening service built with **FastAPI**, **PostgreSQL**, and **SQLAlchemy 2.0** (async).

Submit a long URL, get back a short code. Follow the short code, get redirected to the original.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Project structure](#2-project-structure)
3. [How to run it](#3-how-to-run-it)
4. [API reference](#4-api-reference)
5. [Running the tests](#5-running-the-tests)
6. [Design decisions](#6-design-decisions)
7. [Data model](#7-data-model)
8. [What I would add next](#8-what-i-would-add-next)

---

## 1. What it does

| Method | Path                 | Purpose                                              |
| ------ | -------------------- | ---------------------------------------------------- |
| `POST` | `/shorten`           | Accept a long URL, store it, return a shortened URL   |
| `GET`  | `/{short_code}`      | Redirect to the original URL                          |
| `GET`  | `/stats/{short_code}` | Inspect a link and its visit count without following it |
| `GET`  | `/health`            | Liveness probe                                        |

The first two are the endpoints required by the task. `/stats` and `/health` are small
additions: `/stats` makes the visit counter observable (and gives the test suite a way to
assert on it without following redirects to the public internet), and `/health` is what a
container orchestrator or load balancer would poll.

Interactive API documentation is generated automatically by FastAPI and served at
**http://localhost:8000/docs**.

---

## 2. Project structure

```
url-shortener/
├── app/
│   ├── __init__.py
│   ├── config.py        # Settings loaded from environment / .env
│   ├── database.py      # Async engine, session factory, request dependency
│   ├── models.py        # SQLAlchemy ORM model (short_urls table)
│   ├── schemas.py       # Pydantic request/response models
│   ├── shortcode.py     # Base62 short-code generation
│   ├── crud.py          # Database access layer
│   └── main.py          # FastAPI app: routes, lifespan, error handling
├── tests/
│   ├── conftest.py      # Fixtures: test database, HTTP client
│   ├── test_api.py      # End-to-end tests for every endpoint
│   └── test_shortcode.py # Unit tests for code generation
├── scripts/
│   └── init-test-db.sql # Creates the test database on first container boot
├── docker-compose.yml   # PostgreSQL 16
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

The layering is deliberate: `main.py` only deals with HTTP concerns (status codes,
validation, redirects), `crud.py` only deals with the database, and neither knows much
about the other. That keeps each file short enough to read in one sitting and makes the
data layer testable on its own.

---

## 3. How to run it

### Prerequisites

- Python 3.11 or newer
- PostgreSQL 14+ — either your own instance, or Docker for the bundled `docker-compose.yml`

### Step 1 — Get the code and create a virtual environment

```bash
cd url-shortener

python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Start PostgreSQL

**Option A — Docker (recommended):**

```bash
docker compose up -d
```

This starts PostgreSQL 16 on port `5432` with user `postgres`, password `postgres`, and
databases `urlshortener` and `urlshortener_test`.

**Option B — an existing PostgreSQL install:**

```bash
createdb urlshortener
createdb urlshortener_test   # only needed to run the tests
```

### Step 4 — Configure the app

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

The defaults in `.env.example` match the Docker Compose setup, so if you used Option A
there is nothing to change. Otherwise, point `DATABASE_URL` at your own instance:

```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/urlshortener
```

> The `+asyncpg` suffix is required — it tells SQLAlchemy to use the async driver.

### Step 5 — Run the API

```bash
uvicorn app.main:app --reload
```

The service is now live on **http://localhost:8000**. The `short_urls` table is created
automatically on startup, so there is no migration step to run.

Open **http://localhost:8000/docs** to try the endpoints from the browser.

### Step 6 — Try it from the command line

```bash
# Shorten a URL
curl -X POST http://localhost:8000/shorten \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.wikipedia.org/wiki/Uniform_Resource_Locator"}'
```

```json
{
  "short_code": "2lSMROY",
  "short_url": "http://localhost:8000/2lSMROY",
  "original_url": "https://www.wikipedia.org/wiki/Uniform_Resource_Locator",
  "visit_count": 0,
  "created_at": "2026-08-21T11:29:18.187883Z",
  "last_visited_at": null
}
```

```bash
# Follow it (-i shows the redirect instead of following it)
curl -i http://localhost:8000/2lSMROY
```

```
HTTP/1.1 307 Temporary Redirect
location: https://www.wikipedia.org/wiki/Uniform_Resource_Locator
```

```bash
# Check how many times it has been used
curl http://localhost:8000/stats/2lSMROY
```

---

## 4. API reference

### `POST /shorten`

Stores a long URL and returns its short form.

**Request body**

```json
{ "url": "https://example.com/some/long/path" }
```

`url` must be an absolute `http://` or `https://` URL of at most 2048 characters.

**Responses**

| Status | Meaning |
| ------ | ------- |
| `201 Created` | The short URL, as shown above |
| `422 Unprocessable Entity` | The URL is missing, malformed, or uses an unsupported scheme |
| `503 Service Unavailable` | A unique short code could not be allocated (see [Design decisions](#6-design-decisions)) |

The endpoint is **idempotent**: posting a URL that has already been shortened returns the
existing code rather than minting a second one for the same destination.

### `GET /{short_code}`

Redirects to the URL the code was created from, and increments its visit counter.

| Status | Meaning |
| ------ | ------- |
| `307 Temporary Redirect` | `Location` header holds the original URL |
| `404 Not Found` | No such code |

### `GET /stats/{short_code}`

Returns the same body as `POST /shorten` without redirecting, and **without** counting as
a visit. Returns `404` for an unknown code.

### `GET /health`

Returns `{"status": "ok"}`.

### Errors

Every error response uses the same shape, so clients only need one branch to handle them:

```json
{ "detail": "Short code 'zzzzzzz' not found" }
```

---

## 5. Running the tests

The suite runs against a **real PostgreSQL database** (`urlshortener_test`) rather than an
in-memory SQLite stand-in, because the parts most worth testing — the `UNIQUE` constraint
on `short_code`, the server-side `now()` defaults, and the atomic counter increment —
either behave differently on another engine or do not exist there at all.

```bash
# With PostgreSQL running (Docker Compose creates the test DB automatically)
pytest -v
```

If your test database lives elsewhere, override the connection string:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/urlshortener_test pytest -v
```

**Coverage** — 20 tests across two files:

- code generation: length, alphabet, non-repetition, reserved paths
- `POST /shorten`: creation, idempotency, distinct codes for distinct URLs
- input validation: no scheme, unsupported scheme, malformed, empty, missing body
- `GET /{short_code}`: redirect target, status code, visit counting
- `404` handling: unknown codes, and codes outside the base62 alphabet
- `/stats`: correct counts, and that reading stats does not inflate them

Each test gets a freshly created and dropped schema, so tests do not leak state into one
another.

---

## 6. Design decisions

**Random base62 codes, not an encoded row id.**
Encoding the primary key is the cheaper approach — no uniqueness check needed — but it
makes the URL space enumerable. Anyone could walk `/1`, `/2`, `/3` and read every link
that has ever been shortened. Random 7-character codes cost one extra database round trip
in the rare collision case and keep links unguessable. At 7 characters the space is
62⁷ ≈ 3.5 trillion codes.

**The `UNIQUE` constraint is the arbiter of collisions, not a pre-check.**
The obvious implementation is "generate a code, `SELECT` to see if it exists, `INSERT` if
it doesn't". That is a race: two workers can pass the check simultaneously and one write
silently wins. Instead `crud.create_short_url()` inserts optimistically and catches
`IntegrityError`, retrying with a new code up to `MAX_GENERATION_ATTEMPTS` times. The
database, which is the only component that sees all writes, decides. Exhausting the
retries returns `503` rather than a `500`, because it is a transient capacity signal, not
a bug in the request.

**Visit counting is done in SQL, not in Python.**
`register_visit()` issues `UPDATE ... SET visit_count = visit_count + 1` rather than
reading the row, adding one, and writing it back. Under concurrent redirects the
read-modify-write version loses counts; the SQL version cannot.

**`307`, not `301`.**
A permanent redirect is what most shorteners return, and browsers cache it hard — which
means subsequent clicks never reach the service again. That freezes the visit counter and
makes a link impossible to retire or repoint. A temporary redirect keeps the service in
the loop. `307` specifically (rather than `302`) because it preserves the request method.

**Idempotent `POST /shorten`.**
Shortening the same URL twice returns the same code. This keeps the table from filling
with duplicate rows pointing at one destination, and makes client retries safe. The
trade-off is that two users shortening the same link share a code and therefore share a
visit count — acceptable here, but a per-user product would key the lookup on user id too.

**Async all the way down.**
FastAPI is an ASGI framework, and a URL shortener is almost pure I/O wait. Using
`asyncpg` with SQLAlchemy's async session keeps the event loop free during database calls
instead of blocking a worker thread on each one.

**Codes outside the alphabet get `404`, not `422`.**
A request for `/favicon.ico` cannot possibly be a code this service issued, so it is
rejected before it reaches the database. Answering `404` rather than a validation error is
the honest response — the resource does not exist.

**Reserved paths.** `generate_short_code()` will never return `docs`, `health`, `stats`,
and similar, so a generated code can never shadow a real route.

**`create_all()` on startup instead of migrations.**
For a project this size, creating the table at startup keeps setup to a single command.
A production service would use Alembic so schema changes are versioned and reversible;
that is noted in [What I would add next](#8-what-i-would-add-next).

---

## 7. Data model

A single table:

```
                          Table "public.short_urls"
     Column      |           Type           | Nullable |       Default
-----------------+--------------------------+----------+---------------------
 id              | bigint                   | not null | nextval(...)
 short_code      | character varying(16)    | not null |
 original_url    | character varying(2048)  | not null |
 visit_count     | bigint                   | not null | 0
 created_at      | timestamp with time zone | not null | now()
 last_visited_at | timestamp with time zone |          |
Indexes:
    "short_urls_pkey" PRIMARY KEY, btree (id)
    "ix_short_urls_short_code" UNIQUE, btree (short_code)
    "ix_short_urls_original_url" btree (original_url)
```

- The **unique index on `short_code`** serves double duty: it makes the redirect lookup an
  index scan, and it is the concurrency guard described above.
- The **index on `original_url`** supports the de-duplication lookup that makes `/shorten`
  idempotent.
- **`timestamptz`** rather than naive timestamps, so the stored instant is unambiguous
  regardless of server timezone.

---

## 8. What I would add next

Out of scope for a 1–2 hour exercise, but these are the natural next steps:

- **Alembic migrations** in place of `create_all()`, so schema changes are versioned.
- **Rate limiting** on `POST /shorten` — an open shortener is an attractive target for
  spam and phishing redirects.
- **Custom aliases and expiry dates** (`POST /shorten` accepting an optional `custom_code`
  and `expires_at`), which the current schema accommodates with two more columns.
- **A Redis read-through cache** in front of the redirect lookup. Redirects massively
  outnumber writes, and the code → URL mapping is immutable, so it caches perfectly.
- **Moving visit counting off the request path** onto a queue, so analytics writes never
  add latency to a redirect.
- **A `Dockerfile`** for the API itself, so the whole stack comes up with one command.

---

## Verification

The commands in section 3 were run against PostgreSQL 16.13 before submission; all 20
tests pass and every endpoint was exercised against the live server.
# URL-Shortner
