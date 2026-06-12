# Graph Report - .  (2026-06-12)

## Corpus Check
- Corpus is ~4,397 words - fits in a single context window. You may not need a graph.

## Summary
- 143 nodes · 312 edges · 22 communities (12 shown, 10 thin omitted)
- Extraction: 54% EXTRACTED · 46% INFERRED · 0% AMBIGUOUS · INFERRED: 142 edges (avg confidence: 0.67)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Jobs Scheduler Tests|Jobs Scheduler Tests]]
- [[_COMMUNITY_Offers Scrapers Availability|Offers Scrapers Availability]]
- [[_COMMUNITY_Admin Models Logs|Admin Models Logs]]
- [[_COMMUNITY_MVP Domain Spec|MVP Domain Spec]]
- [[_COMMUNITY_Runtime Architecture|Runtime Architecture]]
- [[_COMMUNITY_Model Enums Mixins|Model Enums Mixins]]
- [[_COMMUNITY_Notification Delivery|Notification Delivery]]
- [[_COMMUNITY_App Config|App Config]]
- [[_COMMUNITY_Django Entry Point|Django Entry Point]]
- [[_COMMUNITY_Commands Package|Commands Package]]
- [[_COMMUNITY_ASGI Bootstrap|ASGI Bootstrap]]
- [[_COMMUNITY_WSGI Bootstrap|WSGI Bootstrap]]
- [[_COMMUNITY_Management Package|Management Package]]
- [[_COMMUNITY_Initial Migration|Initial Migration]]
- [[_COMMUNITY_Scrapers Package|Scrapers Package]]
- [[_COMMUNITY_Services Package|Services Package]]
- [[_COMMUNITY_README Limitations|README Limitations]]

## God Nodes (most connected - your core abstractions)
1. `WatchTarget` - 26 edges
2. `Offer` - 23 edges
3. `AvailabilityEvent` - 21 edges
4. `JobRun` - 14 edges
5. `Product` - 13 edges
6. `Store` - 13 edges
7. `Notification` - 13 edges
8. `check_watch_target()` - 13 edges
9. `MonitorServicesTests` - 13 edges
10. `ParsedOffer` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Pokemony Blau` --semantically_similar_to--> `Private TCG Product Availability Monitor`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `Stack` --semantically_similar_to--> `Preferred Technology Stack`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `Local Setup` --semantically_similar_to--> `Local Development`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `QuerySet` --uses--> `WatchTarget`  [INFERRED]
  monitor/services/scheduler.py → monitor/models.py
- `Preferred Technology Stack` --conceptually_related_to--> `Postgres Service`  [INFERRED]
  AGENTS.md → docker-compose.yml

## Import Cycles
- 1-file cycle: `monitor/services/availability.py -> monitor/services/availability.py`

## Hyperedges (group relationships)
- **Monitoring Backend Architecture** — agents_django_app, agents_django_admin, agents_rq_workers, agents_scheduler, docker_compose_postgres_service, docker_compose_redis_service [INFERRED 0.85]

## Communities (22 total, 10 thin omitted)

### Community 0 - "Jobs Scheduler Tests"
Cohesion: 0.12
Nodes (13): BaseCommand, Command, Command, enqueue_watch_targets(), check_watch_target_job(), enqueue_watch_target_check(), WatchTarget, MonitorServicesTests (+5 more)

### Community 1 - "Offers Scrapers Availability"
Cohesion: 0.20
Nodes (15): Decimal, Offer, WatchTarget, WatchTarget, ParsedOffer, WatchTarget, AvailabilityEvent, ParsedOffer (+7 more)

### Community 2 - "Admin Models Logs"
Cohesion: 0.26
Nodes (13): AvailabilityEventAdmin, JobRunAdmin, NotificationAdmin, OfferAdmin, ProductAdmin, StoreAdmin, WatchTargetAdmin, AvailabilityEvent (+5 more)

### Community 3 - "MVP Domain Spec"
Cohesion: 0.22
Nodes (16): AvailabilityEvent, Core MVP Scope, Data Integrity Rules, Definition of Done, Error Handling, Implementation Priority, JobRun, Manual Matching Strategy (+8 more)

### Community 4 - "Runtime Architecture"
Cohesion: 0.26
Nodes (14): Architecture Overview, Background Jobs, Django Admin, Django App, Local Development, Polling Behavior, Preferred Technology Stack, RQ Workers (+6 more)

### Community 5 - "Model Enums Mixins"
Cohesion: 0.22
Nodes (8): Availability, Channel, EventType, Meta, Mode, ParserType, Status, TimestampedModel

### Community 6 - "Notification Delivery"
Cohesion: 0.67
Nodes (5): Notification, _build_message(), notify_for_event(), send_discord_notification(), send_telegram_notification()

## Knowledge Gaps
- **13 isolated node(s):** `Migration`, `Meta`, `ParserType`, `Mode`, `Availability` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `WatchTarget` connect `Offers Scrapers Availability` to `Jobs Scheduler Tests`, `Admin Models Logs`, `Model Enums Mixins`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `check_watch_target()` connect `Jobs Scheduler Tests` to `Offers Scrapers Availability`, `Admin Models Logs`, `Notification Delivery`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `AvailabilityEvent` connect `Admin Models Logs` to `Jobs Scheduler Tests`, `Offers Scrapers Availability`, `Model Enums Mixins`, `Notification Delivery`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `WatchTarget` (e.g. with `AvailabilityEventAdmin` and `JobRunAdmin`) actually correct?**
  _`WatchTarget` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Offer` (e.g. with `Decimal` and `AvailabilityEventAdmin`) actually correct?**
  _`Offer` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `AvailabilityEvent` (e.g. with `Decimal` and `AvailabilityEventAdmin`) actually correct?**
  _`AvailabilityEvent` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `JobRun` (e.g. with `AvailabilityEventAdmin` and `JobRunAdmin`) actually correct?**
  _`JobRun` has 8 INFERRED edges - model-reasoned connections that need verification._