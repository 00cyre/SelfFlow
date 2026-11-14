# SelfFlow

Local HTTP API for Google Flow image generation. It drives a stealth Chrome session against Flow's internal web API, so requests use your signed-in Flow plan credits rather than paid Gemini API credits.

Image generation only; no video support.

## Install

Requires Google Chrome and Python 3.11+.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Sign in once

```sh
.venv/bin/selfflow --login
```

A dedicated visible Chrome window opens. Click **Create with Google Flow** and finish Google sign-in. The session is saved to `~/.selfflow/chrome-profile`, separate from your personal Chrome. The command exits once Flow is authenticated.

## Serve

```sh
.venv/bin/selfflow
```

Headless Chrome starts on demand and serves `127.0.0.1:8765`.

```sh
curl -s http://127.0.0.1:8765/health

curl -s http://127.0.0.1:8765/v1/images/generations \
  -H 'content-type: application/json' \
  -d '{"prompt":"A quiet harbor at dawn","model":"nano-banana-pro","aspect":"16:9","count":1}'
```

Response: `{"data":[{"id":"...","url":"https://..."}]}`.

Models: `nano-banana-pro`, `nano-banana-2`, `nano-banana-2-lite`.
Aspects: `1:1`, `9:16`, `16:9`, `3:4`, `4:3`.
Optional fields: `seed`, `project_id`, `reference_ids` (up to 4 images per request).

Generation consumes your Flow plan credits. Concurrent calls are serialized because they share one browser session.

## Diagnostics

```sh
.venv/bin/python scripts/dump_cookies.py  # auth cookie names; no values
.venv/bin/python scripts/dump_page.py     # page readiness and loaded scripts
.venv/bin/python scripts/probe.py         # headless session and reCAPTCHA check
.venv/bin/python -m pytest tests/         # payload encoding tests
```

If the Google session expires, run `selfflow --login` again.
