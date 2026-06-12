from __future__ import annotations

import os

import requests
from django.utils import timezone

from monitor.models import AvailabilityEvent, Notification


def notify_for_event(event_id: int) -> None:
    send_telegram_notification(event_id)
    send_discord_notification(event_id)


def send_telegram_notification(event_id: int) -> Notification:
    event = AvailabilityEvent.objects.select_related("offer__store", "offer__product").get(
        pk=event_id
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    notification = Notification.objects.create(
        event=event,
        channel=Notification.Channel.TELEGRAM,
        status=Notification.Status.PENDING,
        destination=chat_id,
        payload_summary=_build_message(event),
    )
    if not token or not chat_id:
        notification.status = Notification.Status.SKIPPED
        notification.error_message = "Telegram credentials not configured."
        notification.save(update_fields=["status", "error_message"])
        return notification

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": notification.payload_summary},
            timeout=10,
        )
        response.raise_for_status()
        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
    except requests.RequestException as exc:
        notification.status = Notification.Status.FAILED
        notification.error_message = str(exc)
    notification.save(update_fields=["status", "sent_at", "error_message"])
    return notification


def send_discord_notification(event_id: int) -> Notification:
    event = AvailabilityEvent.objects.select_related("offer__store", "offer__product").get(
        pk=event_id
    )
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    notification = Notification.objects.create(
        event=event,
        channel=Notification.Channel.DISCORD,
        status=Notification.Status.PENDING,
        destination=webhook_url,
        payload_summary=_build_message(event),
    )
    if not webhook_url:
        notification.status = Notification.Status.SKIPPED
        notification.error_message = "Discord webhook not configured."
        notification.save(update_fields=["status", "error_message"])
        return notification

    try:
        response = requests.post(
            webhook_url,
            json={"content": notification.payload_summary},
            timeout=10,
        )
        response.raise_for_status()
        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
    except requests.RequestException as exc:
        notification.status = Notification.Status.FAILED
        notification.error_message = str(exc)
    notification.save(update_fields=["status", "sent_at", "error_message"])
    return notification


def _build_message(event: AvailabilityEvent) -> str:
    offer = event.offer
    return (
        f"[{event.event_type}] {offer.title} at {offer.store.name}\n"
        f"Status: {event.previous_status or 'n/a'} -> {event.new_status or 'n/a'}\n"
        f"Price: {event.previous_price or 'n/a'} -> {event.new_price or 'n/a'}\n"
        f"URL: {offer.url}"
    )
