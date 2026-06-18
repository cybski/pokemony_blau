from django.core.management.base import BaseCommand, CommandError

from monitor.models import Product, Store, WatchTarget
from monitor.services.scraper_runner import check_watch_target


class Command(BaseCommand):
    help = "Create or update a product, store, and product-page watch target."

    def add_arguments(self, parser):
        parser.add_argument("product_name")
        parser.add_argument("store_name")
        parser.add_argument("base_url")
        parser.add_argument("product_url")
        parser.add_argument(
            "--parser",
            choices=[choice[0] for choice in Store.ParserType.choices],
            default=Store.ParserType.GENERIC_WOOCOMMERCE,
        )
        parser.add_argument("--poll-interval", type=int, default=300)
        parser.add_argument("--pydoll", action="store_true")
        parser.add_argument("--pydoll-headless", action="store_true")
        parser.add_argument("--pydoll-profile-dir")
        parser.add_argument("--pydoll-binary")
        parser.add_argument("--pydoll-wait-seconds", type=int, default=5)
        parser.add_argument("--pydoll-challenge-wait-seconds", type=int, default=60)
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        product, _ = Product.objects.get_or_create(name=options["product_name"])
        store, _ = Store.objects.update_or_create(
            name=options["store_name"],
            defaults={
                "base_url": options["base_url"],
                "parser_type": options["parser"],
                "is_active": True,
            },
        )
        watch_target, created = WatchTarget.objects.update_or_create(
            store=store,
            url=options["product_url"],
            defaults={
                "product": product,
                "mode": WatchTarget.Mode.PRODUCT_PAGE,
                "is_active": True,
                "poll_interval_seconds": options["poll_interval"],
                "parser_config": {
                    "use_pydoll": options["pydoll"],
                    "pydoll_profile_dir": options["pydoll_profile_dir"]
                    or f".pydoll/{store.pk}",
                    "pydoll_headless": options["pydoll_headless"],
                    "pydoll_keep_open": False,
                    "pydoll_wait_seconds": options["pydoll_wait_seconds"],
                    "pydoll_challenge_wait_seconds": options[
                        "pydoll_challenge_wait_seconds"
                    ],
                    "pydoll_binary": options["pydoll_binary"],
                },
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{action} watch target {watch_target.id}: {watch_target.url}")
        )

        if not options["check"]:
            return

        try:
            check_watch_target(watch_target.id)
        except Exception as exc:
            raise CommandError(f"Initial check failed: {exc}") from exc

        offer = watch_target.offers.order_by("-last_seen_at").first()
        if offer is None:
            raise CommandError("Initial check completed but created no offer.")
        self.stdout.write(
            self.style.SUCCESS(
                f"price={offer.price} {offer.currency} "
                f"availability={offer.availability} source={offer.raw.get('source')}"
            )
        )
