# Graph Report - .  (2026-06-21)

## Corpus Check
- Corpus is ~12,645 words - fits in a single context window. You may not need a graph.

## Summary
- 321 nodes · 983 edges · 31 communities (16 shown, 15 thin omitted)
- Extraction: 63% EXTRACTED · 37% INFERRED · 0% AMBIGUOUS · INFERRED: 362 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Management Commands|Management Commands]]
- [[_COMMUNITY_Django Admin|Django Admin]]
- [[_COMMUNITY_Cloudflare Replay|Cloudflare Replay]]
- [[_COMMUNITY_WooCommerce Parsing|WooCommerce Parsing]]
- [[_COMMUNITY_Pydoll Browser|Pydoll Browser]]
- [[_COMMUNITY_Command and Parser Tests|Command and Parser Tests]]
- [[_COMMUNITY_Shoper Front API|Shoper Front API]]
- [[_COMMUNITY_Availability Domain|Availability Domain]]
- [[_COMMUNITY_Scraper Registry|Scraper Registry]]
- [[_COMMUNITY_Notifications|Notifications]]
- [[_COMMUNITY_Project Scope|Project Scope]]
- [[_COMMUNITY_Django App Config|Django App Config]]
- [[_COMMUNITY_Django CLI|Django CLI]]
- [[_COMMUNITY_Offer Deduplication Migration|Offer Deduplication Migration]]
- [[_COMMUNITY_Management Package|Management Package]]
- [[_COMMUNITY_ASGI Entrypoint|ASGI Entrypoint]]
- [[_COMMUNITY_WSGI Entrypoint|WSGI Entrypoint]]
- [[_COMMUNITY_Command Package|Command Package]]
- [[_COMMUNITY_Initial Schema|Initial Schema]]
- [[_COMMUNITY_Parser Type Migration|Parser Type Migration]]
- [[_COMMUNITY_Cloudflare Parser Migration|Cloudflare Parser Migration]]
- [[_COMMUNITY_Shoper Parser Migration|Shoper Parser Migration]]
- [[_COMMUNITY_Scraper Package|Scraper Package]]
- [[_COMMUNITY_Service Package|Service Package]]
- [[_COMMUNITY_PostgreSQL Runtime|PostgreSQL Runtime]]
- [[_COMMUNITY_Redis Runtime|Redis Runtime]]

## God Nodes (most connected - your core abstractions)
1. `WatchTarget` - 82 edges
2. `Offer` - 61 edges
3. `ParsedOffer` - 39 edges
4. `BaseScraper` - 35 edges
5. `AvailabilityEvent` - 34 edges
6. `Store` - 30 edges
7. `CloudflareApiReplayWooCommerceScraper` - 29 edges
8. `Product` - 28 edges
9. `JobRun` - 27 edges
10. `WooCommerceScraperError` - 27 edges

## Surprising Connections (you probably didn't know these)
- `Safe Failure Recording` --semantically_similar_to--> `Conservative Availability Detection`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `ChromiumOptions` --uses--> `WatchTarget`  [INFERRED]
  monitor/scrapers/pydoll_browser.py → monitor/models.py
- `WatchTarget` --uses--> `WatchTarget`  [INFERRED]
  monitor/scrapers/base.py → monitor/models.py
- `Path` --uses--> `WatchTarget`  [INFERRED]
  monitor/scrapers/pydoll_browser.py → monitor/models.py
- `systemd Web Worker and Scheduler Services` --implements--> `Background Store Checks`  [INFERRED]
  docs/deploy-ubuntu-vps.md → AGENTS.md

## Import Cycles
- 1-file cycle: `monitor/scrapers/cloudflare_api_replay_woocommerce.py -> monitor/scrapers/cloudflare_api_replay_woocommerce.py`
- 1-file cycle: `monitor/scrapers/generic_woocommerce.py -> monitor/scrapers/generic_woocommerce.py`
- 1-file cycle: `monitor/scrapers/shoper_front_api.py -> monitor/scrapers/shoper_front_api.py`
- 1-file cycle: `monitor/services/availability.py -> monitor/services/availability.py`

## Hyperedges (group relationships)
- **Availability Monitoring Lifecycle** — agents_watchtarget, agents_offer, agents_availabilityevent, agents_notification, agents_jobrun [EXTRACTED 1.00]
- **Production Runtime Stack** — docs_deploy_ubuntu_vps_systemd_services, docs_deploy_ubuntu_vps_nginx_https, docs_deploy_ubuntu_vps_postgresql_redis [EXTRACTED 1.00]
- **Cloudflare-Aware Monitoring Flow** — readme_battlestash_monitoring, readme_cloudflare_api_replay, readme_pydoll_persistent_chrome, readme_safe_failure_recording [EXTRACTED 1.00]

## Communities (31 total, 15 thin omitted)

### Community 0 - "Management Commands"
Cohesion: 0.06
Nodes (26): BaseCommand, Command, _parse_api_params(), _product_slug(), Command, Command, Command, Command (+18 more)

### Community 1 - "Django Admin"
Cohesion: 0.14
Nodes (31): AvailabilityEventAdmin, JobRunAdmin, Meta, NotificationAdmin, OfferAdmin, OfferMultipleChoiceField, ProductAdmin, ProductAdminForm (+23 more)

### Community 2 - "Cloudflare Replay"
Cohesion: 0.19
Nodes (21): CloudflareBrowserSession, Cookies, Any, Decimal, ParsedOffer, Response, WatchTarget, BaseScraper (+13 more)

### Community 3 - "WooCommerce Parsing"
Cohesion: 0.16
Nodes (17): WatchTarget, Decimal, ParsedOffer, Response, WatchTarget, GenericWooCommerceScraperTests, ParsedOffer, GenericWooCommerceScraper (+9 more)

### Community 4 - "Pydoll Browser"
Cohesion: 0.16
Nodes (20): ChromiumOptions, Any, WatchTarget, Path, capture_browser_api_headers(), collect_browser_state(), fallback_headers_from_browser_state(), _fetch_once() (+12 more)

### Community 5 - "Command and Parser Tests"
Cohesion: 0.12
Nodes (8): AddWatchTargetCommandTests, CloudflareApiReplayWooCommerceScraperTests, _json_response(), _shoper_response(), ShoperFrontApiScraperTests, _text_response(), build_request_url(), TestCase

### Community 6 - "Shoper Front API"
Cohesion: 0.24
Nodes (18): Any, Decimal, ParsedOffer, WatchTarget, RuntimeError, _currency_from_url(), _first_list(), _first_present() (+10 more)

### Community 7 - "Availability Domain"
Cohesion: 0.11
Nodes (20): AvailabilityEvent, Background Store Checks, Conservative Availability Detection, JobRun, Manual Product Matching, Notification, Notification Deduplication and Cooldown, Offer (+12 more)

### Community 8 - "Scraper Registry"
Cohesion: 0.20
Nodes (6): BaseScraper, ParsedOffer, WatchTarget, BaseScraper, GenericScraper, get_scraper()

### Community 9 - "Notifications"
Cohesion: 0.67
Nodes (5): Notification, _build_message(), notify_for_event(), send_discord_notification(), send_telegram_notification()

### Community 10 - "Project Scope"
Cohesion: 0.67
Nodes (3): Backend and Admin MVP, Django Admin, Private TCG Availability Monitor

## Knowledge Gaps
- **22 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `WatchTarget` connect `Management Commands` to `Django Admin`, `Cloudflare Replay`, `WooCommerce Parsing`, `Pydoll Browser`, `Command and Parser Tests`, `Shoper Front API`, `Scraper Registry`?**
  _High betweenness centrality (0.245) - this node is a cross-community bridge._
- **Why does `Offer` connect `Django Admin` to `Management Commands`, `Cloudflare Replay`, `WooCommerce Parsing`, `Command and Parser Tests`, `Shoper Front API`, `Scraper Registry`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `MonitorServicesTests` connect `Management Commands` to `Django Admin`, `Cloudflare Replay`, `WooCommerce Parsing`, `Command and Parser Tests`, `Shoper Front API`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 64 inferred relationships involving `WatchTarget` (e.g. with `ChromiumOptions` and `CloudflareBrowserSession`) actually correct?**
  _`WatchTarget` has 64 INFERRED edges - model-reasoned connections that need verification._
- **Are the 50 inferred relationships involving `Offer` (e.g. with `CloudflareBrowserSession` and `Cookies`) actually correct?**
  _`Offer` has 50 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `ParsedOffer` (e.g. with `CloudflareBrowserSession` and `Cookies`) actually correct?**
  _`ParsedOffer` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `BaseScraper` (e.g. with `CloudflareBrowserSession` and `Cookies`) actually correct?**
  _`BaseScraper` has 27 INFERRED edges - model-reasoned connections that need verification._