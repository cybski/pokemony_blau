from django.core.management.base import BaseCommand

from monitor.jobs import enqueue_watch_target_check
from monitor.services.scheduler import get_due_watch_targets, mark_scheduled


class Command(BaseCommand):
    help = "Enqueue due watch targets for background checking."

    def handle(self, *args, **options):
        count = 0
        for watch_target in get_due_watch_targets():
            enqueue_watch_target_check(watch_target.id)
            mark_scheduled(watch_target)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Enqueued {count} watch target(s)."))
