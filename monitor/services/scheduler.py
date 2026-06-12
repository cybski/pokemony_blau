from __future__ import annotations

from django.db.models import QuerySet
from django.utils import timezone

from monitor.models import WatchTarget


def get_due_watch_targets(now=None) -> QuerySet[WatchTarget]:
    current_time = now or timezone.now()
    return WatchTarget.objects.filter(
        is_active=True,
        next_check_at__lte=current_time,
        store__is_active=True,
    ).select_related("product", "store")


def mark_scheduled(watch_target: WatchTarget) -> WatchTarget:
    watch_target.next_check_at = timezone.now() + timezone.timedelta(
        seconds=watch_target.poll_interval_seconds
    )
    watch_target.save(update_fields=["next_check_at", "updated_at"])
    return watch_target
