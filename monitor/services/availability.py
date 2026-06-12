from __future__ import annotations

from decimal import Decimal

from monitor.models import AvailabilityEvent, Offer
from monitor.scrapers.base import ParsedOffer


def detect_events(old_offer: Offer | None, parsed_offer: ParsedOffer) -> list[dict]:
    events: list[dict] = []

    if old_offer is None:
        events.append(
            {
                "event_type": AvailabilityEvent.EventType.FOUND,
                "previous_status": "",
                "new_status": parsed_offer.availability,
                "previous_price": None,
                "new_price": parsed_offer.price,
            }
        )
        return events

    if old_offer.availability != parsed_offer.availability:
        events.append(
            {
                "event_type": AvailabilityEvent.EventType.AVAILABILITY_CHANGED,
                "previous_status": old_offer.availability,
                "new_status": parsed_offer.availability,
                "previous_price": old_offer.price,
                "new_price": parsed_offer.price,
            }
        )

    old_price = _normalize_price(old_offer.price)
    new_price = _normalize_price(parsed_offer.price)
    if old_price is not None and new_price is not None and old_price != new_price:
        events.append(
            {
                "event_type": AvailabilityEvent.EventType.PRICE_CHANGED,
                "previous_status": old_offer.availability,
                "new_status": parsed_offer.availability,
                "previous_price": old_price,
                "new_price": new_price,
            }
        )

    return events


def should_notify(event: AvailabilityEvent) -> bool:
    return (
        event.new_status == Offer.Availability.IN_STOCK
        and event.previous_status != Offer.Availability.IN_STOCK
    )


def _normalize_price(value: Decimal | None) -> Decimal | None:
    return value.quantize(Decimal("0.01")) if value is not None else None
