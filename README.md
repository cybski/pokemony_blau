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
- Pydoll browser fallback

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
uv run python manage.py add_watch_target <store_name> <base_url> <watch_url> --mode <mode> --check
uv run python manage.py prime_pydoll_profile <watch_target_id>
uv run python manage.py run_pydoll_monitor <watch_target_id>
uv run python manage.py test
```

## Verify BattleStash price monitoring

Start the database, migrate, and create the BattleStash watch target:

```bash
docker compose up -d
uv run python manage.py migrate
uv run python manage.py add_watch_target \
  "BattleStash" \
  "https://battlestash.pl" \
  "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/" \
  --mode product_page \
  --product-name "Pokemon Chaos Rising Booster Box" \
  --parser cloudflare_api_replay_woocommerce \
  --poll-interval 15 \
  --pydoll \
  --pydoll-challenge-wait-seconds 15
```

The command prints the new watch target ID. If BattleStash returns a Cloudflare challenge,
open a headed browser using that ID:

```bash
uv run python manage.py prime_pydoll_profile <watch_target_id>
```

Complete any challenge in the browser. Return to the terminal and press Enter. The browser
session is stored under `.pydoll/`.

Verify price detection:

```bash
uv run python manage.py check_watch_target <watch_target_id>
```

The command prints the detected `price`, `availability`, and source. The parser tries:

1. WooCommerce public Store API using the product slug.
2. Product-page `Product` JSON-LD if the Store API fails.
3. Branded Google Chrome using the persistent browser profile if enabled.
4. Cloudflare API replay parser when browser clearance cookies are required for API calls.

If every method is blocked, the check fails and records a failed `JobRun` instead of
recording false stock data. Inspect the failure in Django Admin or run the check command
again after priming the profile.

## Category and search discovery

Use `category_page` or `search_page` targets to discover every store product returned by
the configured API query. Discovered rows are stored as store offers and are not mapped to
internal products automatically.

```bash
uv run python manage.py add_watch_target \
  "BattleStash" \
  "https://battlestash.pl" \
  "https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/" \
  --mode category_page \
  --parser cloudflare_api_replay_woocommerce \
  --api-param "category=712" \
  --poll-interval 300 \
  --pydoll
```

For search pages, pass the query through `--api-param`:

```bash
uv run python manage.py add_watch_target \
  "BattleStash" \
  "https://battlestash.pl" \
  "https://battlestash.pl/?s=chaos" \
  --mode search_page \
  --parser generic_woocommerce \
  --api-param "search=chaos" \
  --api-param "per_page=100"
```

In Django Admin, open Offers, assign an internal Product, and check
`mapping_confirmed`. Notifications are sent only for mapped and confirmed offers.

Pydoll connects directly to installed Google Chrome over CDP without WebDriver. The default
configuration uses headed mode and a persistent browser profile. It does not guarantee
Cloudflare clearance.

For the most coherent browser identity, keep one headed branded Chrome process open:

```bash
uv run python manage.py run_pydoll_monitor <watch_target_id>
```

If a challenge appears, complete it in that Chrome window. The process checks the target
again at its configured polling interval using the same browser process and profile.
Pydoll profiles cannot be opened by multiple processes simultaneously.

## Cloudflare API replay parser

Use `cloudflare_api_replay_woocommerce` when a WooCommerce Store API endpoint works
after a browser clears Cloudflare, but later returns `401`/`403` or challenge HTML
when the clearance expires.

Example `WatchTarget.parser_config`:

```json
{
  "api_url": "https://battlestash.pl/wp-json/wc/store/products",
  "api_params": {
    "category": "712"
  },
  "browser_url": "https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/",
  "refresh_status_codes": [401, 403],
  "pydoll_profile_dir": ".pydoll/battlestash",
  "pydoll_headless": false,
  "pydoll_challenge_wait_seconds": 180
}
```

First check opens Chrome through Pydoll, waits for Cloudflare to clear, captures cookies
and browser-like headers, then replays the API request with `httpx`. Later checks reuse
persisted cookies/headers and refresh the browser session only when the API is blocked
again. Add `product_slug` only for single product-page monitoring; omit it for
category/search discovery.

`JobRun.debug_payload` stores safe metadata only: source, HTTP status, refresh count,
item count, and session counts. It does not store cookies or replayed request headers.

To poll continuously, run Redis and an RQ worker, then invoke the scheduler command from
cron every minute:

```bash
uv run python manage.py rqworker default
uv run python manage.py enqueue_due_checks
```

## Current limitations

- WooCommerce Store API, product JSON-LD, and Cloudflare API replay are supported.
- The persistent Chrome monitor requires an active desktop session.
- Cloudflare clearance cookies expire and may require solving another challenge.
- Manual product mapping only; assign `Offer.product` and confirm `mapping_confirmed`
  in Django Admin.
- Notification delivery is minimal Telegram/Discord integration.
- Scheduler is a command, not a long-running daemon.
