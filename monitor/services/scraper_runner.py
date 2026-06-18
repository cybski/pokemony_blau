from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from monitor.models import AvailabilityEvent, JobRun, Offer, WatchTarget
from monitor.scrapers.registry import get_scraper
from monitor.services.availability import detect_events, should_notify
from monitor.services.notifications import notify_for_event


def check_watch_target(watch_target_id: int) -> None:
    watch_target = WatchTarget.objects.select_related("product", "store").get(pk=watch_target_id)
    job_run = JobRun.objects.create(
        store=watch_target.store,
        watch_target=watch_target,
        status=JobRun.Status.RUNNING,
        started_at=timezone.now(),
        parser_name=watch_target.store.parser_type,
    )

    try:
        scraper = get_scraper(
            parser_type=watch_target.store.parser_type,
            timeout_seconds=watch_target.store.timeout_seconds,
        )
        parsed_offers, debug_payload = scraper.parse_watch_target(watch_target)

        created_events: list[AvailabilityEvent] = []
        with transaction.atomic():
            for parsed_offer in parsed_offers:
                old_offer = Offer.objects.filter(
                    store=watch_target.store,
                    watch_target=watch_target,
                    url=parsed_offer.url,
                ).first()

                defaults = {
                    "product": watch_target.product or (old_offer.product if old_offer else None),
                    "title": parsed_offer.title,
                    "price": parsed_offer.price,
                    "currency": parsed_offer.currency,
                    "availability": parsed_offer.availability,
                    "raw": parsed_offer.raw,
                    "last_seen_at": timezone.now(),
                    "last_changed_at": timezone.now(),
                }
                if old_offer and (
                    old_offer.availability == parsed_offer.availability
                    and old_offer.price == parsed_offer.price
                ):
                    defaults["last_changed_at"] = old_offer.last_changed_at

                offer, created = Offer.objects.update_or_create(
                    store=watch_target.store,
                    watch_target=watch_target,
                    url=parsed_offer.url,
                    defaults=defaults,
                )

                for event_data in detect_events(None if created else old_offer, parsed_offer):
                    event = AvailabilityEvent.objects.create(offer=offer, **event_data)
                    created_events.append(event)

        watch_target.last_checked_at = timezone.now()
        watch_target.save(update_fields=["last_checked_at", "updated_at"])
        job_run.status = JobRun.Status.SUCCESS
        job_run.finished_at = timezone.now()
        job_run.http_status = debug_payload.get("http_status")
        job_run.items_found = len(parsed_offers)
        job_run.debug_payload = debug_payload
        job_run.save(
            update_fields=[
                "status",
                "finished_at",
                "http_status",
                "items_found",
                "debug_payload",
            ]
        )

        for event in created_events:
            if should_notify(event):
                notify_for_event(event.id)
    except Exception as exc:
        watch_target.last_checked_at = timezone.now()
        watch_target.save(update_fields=["last_checked_at", "updated_at"])
        job_run.status = JobRun.Status.FAILED
        job_run.finished_at = timezone.now()
        job_run.error_message = str(exc)
        job_run.debug_payload = {
            "watch_target_id": watch_target_id,
            "url": watch_target.url,
        }
        job_run.save(
            update_fields=["status", "finished_at", "error_message", "debug_payload"]
        )
        raise
