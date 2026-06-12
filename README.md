# Pokemony Blau

Private TCG product availability monitor scaffold. Backend only: Django Admin, background checks, offer state, event logging, and notification hooks.

## Stack

- Python 3.14
- `uv`
- Django
- PostgreSQL
- Redis + `django-rq`
- `httpx`
- `beautifulsoup4`
- `selectolax`
- Playwright Python scaffold

## Local setup

```bash
cp .env.example .env
uv sync
docker compose up -d
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

## Run

```bash
uv run python manage.py runserver
uv run python manage.py rqworker default
uv run python manage.py enqueue_due_checks
uv run python manage.py check_watch_target <watch_target_id>
uv run playwright install chromium
uv run python manage.py test
```

## Current limitations

- Generic placeholder scraper only.
- Availability currently defaults to `unknown`.
- Manual product mapping only.
- Notification delivery is minimal Telegram/Discord integration.
- Scheduler is a command, not a long-running daemon.
