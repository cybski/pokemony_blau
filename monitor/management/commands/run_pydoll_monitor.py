import time

from django.core.management.base import BaseCommand, CommandError

from monitor.models import WatchTarget
from monitor.scrapers.pydoll_browser import PERSISTENT_PYDOLL_RUNTIME
from monitor.services.scraper_runner import check_watch_target


class Command(BaseCommand):
    help = "Continuously check one target using the same headed Pydoll Chrome session."

    def add_arguments(self, parser):
        parser.add_argument("watch_target_id", type=int)
        parser.add_argument("--interval", type=int)

    def handle(self, *args, **options):
        watch_target = WatchTarget.objects.get(pk=options["watch_target_id"])
        config = watch_target.parser_config
        config.update(
            {
                "use_pydoll": True,
                "pydoll_headless": False,
                "pydoll_keep_open": True,
            }
        )
        watch_target.parser_config = config
        watch_target.save(update_fields=["parser_config", "updated_at"])
        interval = options["interval"] or watch_target.poll_interval_seconds

        self.stdout.write(
            f"Monitoring target {watch_target.id} every {interval}s using persistent Pydoll."
        )
        self.stdout.write("Keep this process and the Chrome window open. Press Ctrl-C to stop.")

        try:
            while True:
                try:
                    check_watch_target(watch_target.id)
                    offer = watch_target.offers.order_by("-last_seen_at").first()
                    if offer:
                        self.stdout.write(
                            f"price={offer.price} {offer.currency} "
                            f"availability={offer.availability} source={offer.raw.get('source')}"
                        )
                except Exception as exc:
                    self.stderr.write(f"Check failed: {exc}")
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("Stopping persistent Pydoll monitor.")
        finally:
            try:
                PERSISTENT_PYDOLL_RUNTIME.close()
            except Exception as exc:
                raise CommandError(f"Failed to close persistent Pydoll: {exc}") from exc
