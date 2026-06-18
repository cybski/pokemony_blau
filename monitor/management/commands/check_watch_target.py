from django.core.management.base import BaseCommand, CommandError

from monitor.models import WatchTarget
from monitor.services.scraper_runner import check_watch_target


class Command(BaseCommand):
    help = "Run one watch target check synchronously."

    def add_arguments(self, parser):
        parser.add_argument("watch_target_id", type=int)

    def handle(self, *args, **options):
        watch_target_id = options["watch_target_id"]
        try:
            check_watch_target(watch_target_id)
        except Exception as exc:
            raise CommandError(f"Watch target {watch_target_id} failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(f"Watch target {watch_target_id} checked successfully.")
        )
        watch_target = WatchTarget.objects.get(pk=watch_target_id)
        for offer in watch_target.offers.order_by("-last_seen_at"):
            self.stdout.write(
                f"- {offer.title}\n"
                f"  price={offer.price} {offer.currency}\n"
                f"  availability={offer.availability}\n"
                f"  url={offer.url}\n"
                f"  source={offer.raw.get('source', 'unknown')}"
            )
