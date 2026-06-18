# AGENTS.md

## Project purpose

This project is a private TCG product availability monitor.

The goal is to detect when selected products appear or become available on selected online stores, then notify the owner quickly enough to buy them before they sell out.

This is **not** a public price comparison site, marketplace, SEO site, or storefront.

## Core MVP scope

Build only the backend/admin foundation needed to:

1. Define products to monitor.
2. Define stores.
3. Define watch targets for specific product/search/category pages.
4. Fetch pages from stores in background jobs.
5. Parse availability, price, title, and URL.
6. Manually map store results to internal products.
7. Detect availability changes.
8. Send notifications when a product becomes available.
9. Inspect job runs, parser output, errors, and offer state in the admin panel.

## Preferred technology stack

Use Python unless there is a strong reason not to.

Preferred stack:

- Python
- Django
- Django Admin
- PostgreSQL
- Redis
- RQ or django-rq
- httpx for normal HTTP requests
- BeautifulSoup or selectolax for HTML parsing
- Pydoll for JS-rendered pages only
- Docker Compose for local development
- Telegram bot and/or Discord webhook for notifications

Avoid building a separate frontend unless explicitly requested. Django Admin is enough for MVP.

## Architecture overview

The system should have these main parts:

```text
Django app
  ├── Models
  ├── Django Admin
  ├── Scraper services
  ├── Parser implementations
  ├── Notification services
  ├── Management commands
  └── RQ job definitions

PostgreSQL
  └── Persistent data

Redis
  └── Job queue

RQ workers
  └── Background store checks

Scheduler
  └── Periodically enqueues due watch targets
```

## Main concepts

### Product

An internal item the owner wants to monitor.

Examples:

- Pokémon 151 Booster Bundle
- One Piece OP-09 Booster Box
- Disney Lorcana Booster Box
- Pokémon Prismatic Evolutions ETB

Products do not need categories, sets, or games in MVP unless they are useful as plain metadata.

### Store

A website/shop that may sell monitored products.

A store has:

- name
- base URL
- parser type
- active/inactive flag
- rate limit
- timeout
- optional notes

### WatchTarget

The most important entity in the MVP.

A watch target defines exactly what to check and how.

Examples:

- A specific product URL.
- A store search result page.
- A category page.
- A preconfigured URL for “Lorcana booster”.

Fields should include:

- product, nullable if target can discover multiple products
- store
- URL
- mode: `product_page`, `search_page`, `category_page`
- parser type / parser config
- active flag
- polling interval
- last checked timestamp
- next check timestamp
- notes

### Offer

The current known state of a product/store result.

Fields should include:

- product
- store
- watch target
- title as found on store
- URL
- price
- currency
- availability
- last seen timestamp
- last changed timestamp
- raw parsed data

Availability values should be normalized:

```text
unknown
missing
out_of_stock
in_stock
preorder
```

### AvailabilityEvent

A recorded change in availability or price.

Important transitions:

```text
missing -> in_stock
out_of_stock -> in_stock
preorder -> in_stock
in_stock -> out_of_stock
price_changed
```

Only meaningful changes should create events.

### JobRun

Every background check should create a job run record.

Track:

- status: `queued`, `running`, `success`, `failed`, `partial`
- started at
- finished at
- store
- watch target
- error message
- HTTP status
- items found
- parser name
- raw summary / debug payload

This is essential for debugging broken scrapers.

### Notification

A record of sent or failed notifications.

Fields should include:

- event
- channel: `telegram`, `discord`, `email`
- status: `pending`, `sent`, `failed`, `skipped`
- sent at
- error message
- destination
- payload summary

## Recommended Django apps

Use one main Django app initially, for example:

```text
monitor/
  models.py
  admin.py
  jobs.py
  services/
    scheduler.py
    scraper_runner.py
    availability.py
    notifications.py
  scrapers/
    base.py
    generic.py
    generic_woocommerce.py
    generic_shopify.py
  management/
    commands/
      run_scheduler.py
      check_watch_target.py
      enqueue_due_checks.py
```

Do not over-split the project too early.

## Scraper design

Each scraper should return normalized data using a shared structure.

Example:

```python
@dataclass
class ParsedOffer:
    title: str
    url: str
    price: Decimal | None
    currency: str
    availability: str
    raw: dict
```

Each store-specific parser should be isolated.

Preferred flow:

```text
fetch HTML
  -> parse raw store data
  -> normalize availability
  -> normalize price
  -> update offer
  -> detect event
  -> maybe notify
```

Do not mix scraping, database writes, and notification sending inside one large function. Keep these as separate services.

## Matching strategy

MVP matching is manual.

Do not implement complex fuzzy matching unless requested.

Support:

- manually assigning an offer or watch target to a product
- storing raw title/URL from the store
- marking a mapping as confirmed

If an item cannot be matched safely, leave it unmatched and expose it in admin.

Accuracy matters more than automation.

## Background jobs

Use background jobs for all store checks.

Do not perform scraping inside web request/response flows except for an explicit admin “test now” action.

Recommended jobs:

```text
check_watch_target
enqueue_due_watch_targets
send_notification
```

The scheduler should:

1. Find active watch targets where `next_check_at <= now`.
2. Enqueue checks.
3. Update scheduling metadata.
4. Respect per-store rate limits.

## Notification rules

Avoid spam.

Default rule:

Notify only when availability changes into `in_stock`.

Examples:

```text
out_of_stock -> in_stock: notify
missing -> in_stock: notify
in_stock -> in_stock: do not notify
unknown -> in_stock: notify, but mark confidence if needed
price change while in stock: optional, disabled by default
```

Add a cooldown per product/store/watch target.

Telegram and Discord are preferred for MVP.

## Admin requirements

Django Admin should allow the owner to:

- add/edit products
- add/edit stores
- add/edit watch targets
- run a check manually
- view current offers
- view availability events
- view job runs
- view notification logs
- inspect parser errors
- disable broken watch targets
- update manual product mappings

Admin usability is more important than public UI.

## Data integrity rules

- Never treat `unknown` as `in_stock`.
- Never notify on every polling cycle.
- Never overwrite useful raw debug data without keeping the latest parser output.
- Always record failed job runs.
- Store timestamps for all checks and changes.
- Prefer conservative availability detection over false positives.

## Polling behavior

Respect stores.

Use configurable polling intervals.

Recommended defaults:

```text
normal target: every 5-15 minutes
high-priority target: every 1-3 minutes
low-priority target: every 30-60 minutes
broken target: disabled or backed off
```

Do not hammer a store with parallel requests.

Use timeouts, retries, and exponential backoff for failures.

## Error handling

All scraper errors should be captured in `JobRun`.

A failed store check should not crash the worker process.

Store enough information to debug:

- exception type
- message
- HTTP status
- parser name
- target URL
- short response snippet if safe
- timestamp

## What not to build unless explicitly requested

Do not build:

- public frontend
- SEO pages
- user accounts
- categories/sets/games taxonomy
- collection/portfolio tracking
- marketplace
- affiliate tracking
- card scanner
- price comparison analytics
- blog
- public API
- complex fuzzy matching
- payment/subscription features

## Coding conventions

- Keep code simple and explicit.
- Prefer readable service functions over premature abstractions.
- Use type hints for service-layer code.
- Keep parser logic isolated per store.
- Keep database writes in services, not deeply inside parser classes.
- Add tests for availability detection and parser normalization.
- Use environment variables for secrets and tokens.
- Never commit secrets.

## Testing expectations

At minimum, add tests for:

- availability transition detection
- notification deduplication/cooldown
- price parsing
- parser output normalization
- scheduler selecting due watch targets
- failed job run recording

Parser tests may use saved HTML fixtures.

## Local development

Prefer Docker Compose with services:

```text
web
worker
scheduler
postgres
redis
```

Provide commands for:

```text
migrate database
create superuser
run web server
run worker
run scheduler
run one watch target manually
```

## Implementation priority

Build in this order:

1. Django project setup.
2. Core models.
3. Django Admin.
4. Manual products, stores, and watch targets.
5. One generic HTTP fetcher.
6. One simple parser.
7. Manual “run check now”.
8. JobRun logging.
9. Offer updates.
10. AvailabilityEvent detection.
11. Telegram or Discord notifications.
12. RQ worker.
13. Scheduler.
14. Store-specific parsers.
15. Pydoll support only where needed.

## Definition of done for MVP

MVP is done when:

- The owner can add a product in Django Admin.
- The owner can add a store.
- The owner can add a watch target URL.
- The system checks that URL periodically.
- The system records success/failure logs.
- The system updates current offer state.
- The system detects `out_of_stock -> in_stock`.
- The system sends a Telegram or Discord notification.
- The owner can debug parser failures in admin.

Update this document every time it makes sense, for example some points are no longer necessary or requirements change.
