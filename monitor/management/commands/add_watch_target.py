from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from monitor.models import Product, Store, WatchTarget
from monitor.services.scraper_runner import check_watch_target


class Command(BaseCommand):
    help = "Create or update a store watch target."

    def add_arguments(self, parser):
        parser.add_argument("store_name")
        parser.add_argument("base_url")
        parser.add_argument("watch_url")
        parser.add_argument(
            "--parser",
            choices=[choice[0] for choice in Store.ParserType.choices],
            default=Store.ParserType.GENERIC_WOOCOMMERCE,
        )
        parser.add_argument("--poll-interval", type=int, default=300)
        parser.add_argument(
            "--mode",
            choices=[choice[0] for choice in WatchTarget.Mode.choices],
            required=True,
        )
        parser.add_argument("--product-name")
        parser.add_argument("--pydoll", action="store_true")
        parser.add_argument("--pydoll-headless", action="store_true")
        parser.add_argument("--pydoll-profile-dir")
        parser.add_argument("--pydoll-binary")
        parser.add_argument("--pydoll-wait-seconds", type=int, default=30)
        parser.add_argument("--pydoll-challenge-wait-seconds", type=int, default=60)
        parser.add_argument("--api-url")
        parser.add_argument("--browser-url")
        parser.add_argument("--product-slug")
        parser.add_argument(
            "--api-param",
            action="append",
            default=[],
            help="Replay API query param in key=value form. Repeat for multiple params.",
        )
        parser.add_argument(
            "--refresh-status-code",
            action="append",
            type=int,
            default=[],
            help="HTTP status code that should trigger a browser refresh. Repeat as needed.",
        )
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        if options["mode"] == WatchTarget.Mode.PRODUCT_PAGE and not options["product_name"]:
            raise CommandError("--product-name is required for product_page watch targets.")

        product = None
        if options["mode"] == WatchTarget.Mode.PRODUCT_PAGE:
            product, _ = Product.objects.get_or_create(name=options["product_name"])

        store, _ = Store.objects.update_or_create(
            name=options["store_name"],
            defaults={
                "base_url": options["base_url"],
                "parser_type": options["parser"],
                "is_active": True,
            },
        )
        parser_config = {
            "use_pydoll": options["pydoll"],
            "pydoll_profile_dir": options["pydoll_profile_dir"]
            or f".pydoll/{store.pk}",
            "pydoll_headless": options["pydoll_headless"],
            "pydoll_keep_open": False,
            "pydoll_wait_seconds": options["pydoll_wait_seconds"],
            "pydoll_challenge_wait_seconds": options["pydoll_challenge_wait_seconds"],
            "pydoll_binary": options["pydoll_binary"],
        }
        if options["parser"] == Store.ParserType.GENERIC_WOOCOMMERCE:
            if options["api_url"]:
                parser_config["store_api_url"] = options["api_url"]
            if options["mode"] == WatchTarget.Mode.PRODUCT_PAGE:
                parser_config["product_slug"] = options["product_slug"] or _product_slug(
                    options["watch_url"]
                )
            if options["mode"] in (
                WatchTarget.Mode.CATEGORY_PAGE,
                WatchTarget.Mode.SEARCH_PAGE,
            ) and options["api_param"]:
                parser_config["api_params"] = _parse_api_params(options["api_param"])

        if options["parser"] == Store.ParserType.CLOUDFLARE_API_REPLAY_WOOCOMMERCE:
            parser_config.update(
                {
                    "api_url": options["api_url"]
                    or f"{store.base_url.rstrip('/')}/wp-json/wc/store/products",
                    "browser_url": options["browser_url"] or options["watch_url"],
                }
            )
            if options["mode"] == WatchTarget.Mode.PRODUCT_PAGE:
                parser_config["product_slug"] = options["product_slug"] or _product_slug(
                    options["watch_url"]
                )
            if options["api_param"]:
                parser_config["api_params"] = _parse_api_params(options["api_param"])
            if options["refresh_status_code"]:
                parser_config["refresh_status_codes"] = options["refresh_status_code"]

        watch_target, created = WatchTarget.objects.update_or_create(
            store=store,
            url=options["watch_url"],
            defaults={
                "product": product,
                "mode": options["mode"],
                "is_active": True,
                "poll_interval_seconds": options["poll_interval"],
                "parser_config": parser_config,
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} watch target {watch_target.id}: {watch_target.url}"
            )
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


def _parse_api_params(raw_params: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for raw_param in raw_params:
        if "=" not in raw_param:
            raise CommandError(
                f"Invalid --api-param value: {raw_param!r}. Use key=value."
            )
        key, value = raw_param.split("=", 1)
        if not key:
            raise CommandError(f"Invalid --api-param value: {raw_param!r}. Empty key.")
        params[key] = value
    return params


def _product_slug(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if not path_parts:
        raise CommandError("Could not derive product slug from watch_url.")
    return path_parts[-1]
