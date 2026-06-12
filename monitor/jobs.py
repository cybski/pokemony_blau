from __future__ import annotations

import django_rq

from monitor.models import JobRun, WatchTarget
from monitor.services.scraper_runner import check_watch_target


def enqueue_watch_target_check(watch_target_id: int):
    watch_target = WatchTarget.objects.select_related("store").get(pk=watch_target_id)
    JobRun.objects.create(
        store=watch_target.store,
        watch_target=watch_target,
        status=JobRun.Status.QUEUED,
        parser_name=watch_target.store.parser_type,
        debug_payload={"watch_target_id": watch_target_id},
    )
    queue = django_rq.get_queue("default")
    return queue.enqueue(check_watch_target_job, watch_target_id)


def check_watch_target_job(watch_target_id: int) -> None:
    check_watch_target(watch_target_id)
