import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from monitor.models import AvailabilityEvent, JobRun, Offer, Product, Store, WatchTarget
from monitor.scrapers.cloudflare_api_replay_woocommerce import (
    CloudflareApiReplayWooCommerceError,
    CloudflareApiReplayWooCommerceScraper,
    build_cookie_jar,
    replay_headers,
)
from monitor.scrapers.generic_woocommerce import (
    GenericWooCommerceScraper,
    WooCommerceScraperError,
)
from monitor.scrapers.pydoll_browser import CloudflareBrowserSession, pydoll_options
from monitor.scrapers.pydoll_browser import _go_to
from monitor.scrapers.registry import get_scraper
from monitor.scrapers.shoper_front_api import (
    ShoperFrontApiScraper,
    build_request_url,
)
from monitor.services.scheduler import get_due_watch_targets
from monitor.services.scraper_runner import check_watch_target


class MonitorServicesTests(TestCase):
    def setUp(self) -> None:
        self.product = Product.objects.create(name="Pokemon 151 Booster Bundle")
        self.store = Store.objects.create(
            name="Test Store",
            base_url="https://example.com",
        )

    def test_get_due_watch_targets_returns_only_active_due_targets(self):
        now = timezone.now()
        due = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/due",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
            next_check_at=now - timezone.timedelta(minutes=1),
        )
        WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/future",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
            next_check_at=now + timezone.timedelta(minutes=5),
        )
        WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/inactive",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
            is_active=False,
            next_check_at=now - timezone.timedelta(minutes=5),
        )

        result = list(get_due_watch_targets(now=now))

        self.assertEqual(result, [due])

    @patch("monitor.services.scraper_runner.notify_for_event")
    @patch("monitor.scrapers.generic.GenericScraper.fetch")
    def test_offer_update_creates_availability_event_without_unmapped_notify(
        self,
        mock_fetch,
        mock_notify,
    ):
        watch_target = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/product",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
        )
        Offer.objects.create(
            product=self.product,
            store=self.store,
            watch_target=watch_target,
            title="Pokemon 151 Booster Bundle",
            url="https://example.com/product",
            price=Decimal("10.00"),
            availability=Offer.Availability.OUT_OF_STOCK,
        )
        mock_fetch.return_value = (
            "<html><head><title>Pokemon 151 Booster Bundle</title></head><body></body></html>",
            200,
        )

        check_watch_target(watch_target.id)

        event = AvailabilityEvent.objects.get()
        offer = Offer.objects.get()
        self.assertEqual(offer.availability, Offer.Availability.UNKNOWN)
        self.assertEqual(event.event_type, AvailabilityEvent.EventType.AVAILABILITY_CHANGED)
        self.assertEqual(event.previous_status, Offer.Availability.OUT_OF_STOCK)
        self.assertEqual(event.new_status, Offer.Availability.UNKNOWN)
        mock_notify.assert_not_called()

    @patch("monitor.services.scraper_runner.notify_for_event")
    @patch("monitor.scrapers.generic_woocommerce.GenericWooCommerceScraper.fetch_store_api")
    def test_mapped_confirmed_in_stock_transition_notifies(
        self,
        mock_fetch_store_api,
        mock_notify,
    ):
        self.store.parser_type = Store.ParserType.GENERIC_WOOCOMMERCE
        self.store.save(update_fields=["parser_type"])
        watch_target = WatchTarget.objects.create(
            store=self.store,
            url="https://example.com/category",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
        )
        Offer.objects.create(
            product=self.product,
            mapping_confirmed=True,
            store=self.store,
            watch_target=watch_target,
            title="Pokemon 151 Booster Bundle",
            url="https://example.com/product",
            price=Decimal("10.00"),
            availability=Offer.Availability.OUT_OF_STOCK,
        )
        mock_fetch_store_api.return_value = (
            [
                {
                    "name": "Pokemon 151 Booster Bundle",
                    "slug": "pokemon-151-booster-bundle",
                    "permalink": "https://example.com/product",
                    "is_in_stock": True,
                    "prices": {"price": "1000", "currency_minor_unit": 2},
                }
            ],
            200,
        )

        check_watch_target(watch_target.id)

        mock_notify.assert_called_once()

    @patch("monitor.services.scraper_runner.notify_for_event")
    @patch("monitor.scrapers.generic_woocommerce.GenericWooCommerceScraper.fetch_store_api")
    def test_mapped_but_unconfirmed_in_stock_transition_does_not_notify(
        self,
        mock_fetch_store_api,
        mock_notify,
    ):
        self.store.parser_type = Store.ParserType.GENERIC_WOOCOMMERCE
        self.store.save(update_fields=["parser_type"])
        watch_target = WatchTarget.objects.create(
            store=self.store,
            url="https://example.com/category",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
        )
        Offer.objects.create(
            product=self.product,
            mapping_confirmed=False,
            store=self.store,
            watch_target=watch_target,
            title="Pokemon 151 Booster Bundle",
            url="https://example.com/product",
            availability=Offer.Availability.OUT_OF_STOCK,
        )
        mock_fetch_store_api.return_value = (
            [
                {
                    "name": "Pokemon 151 Booster Bundle",
                    "slug": "pokemon-151-booster-bundle",
                    "permalink": "https://example.com/product",
                    "is_in_stock": True,
                    "prices": {"price": "1000", "currency_minor_unit": 2},
                }
            ],
            200,
        )

        check_watch_target(watch_target.id)

        mock_notify.assert_not_called()

    @patch("monitor.scrapers.generic_woocommerce.GenericWooCommerceScraper.fetch_store_api")
    def test_same_store_url_updates_one_offer_across_watch_targets(
        self,
        mock_fetch_store_api,
    ):
        self.store.parser_type = Store.ParserType.GENERIC_WOOCOMMERCE
        self.store.save(update_fields=["parser_type"])
        first_target = WatchTarget.objects.create(
            store=self.store,
            url="https://example.com/category-a",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
        )
        second_target = WatchTarget.objects.create(
            store=self.store,
            url="https://example.com/category-b",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
        )
        mock_fetch_store_api.return_value = (
            [
                {
                    "name": "Pokemon 151 Booster Bundle",
                    "slug": "pokemon-151-booster-bundle",
                    "permalink": "https://example.com/product",
                    "is_in_stock": True,
                    "prices": {"price": "1000", "currency_minor_unit": 2},
                }
            ],
            200,
        )

        check_watch_target(first_target.id)
        check_watch_target(second_target.id)

        offer = Offer.objects.get()
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(offer.watch_target, second_target)
        self.assertIsNone(offer.product)

    @patch("monitor.scrapers.generic_woocommerce.GenericWooCommerceScraper.fetch_store_api")
    def test_existing_manual_mapping_survives_category_check(
        self,
        mock_fetch_store_api,
    ):
        self.store.parser_type = Store.ParserType.GENERIC_WOOCOMMERCE
        self.store.save(update_fields=["parser_type"])
        watch_target = WatchTarget.objects.create(
            store=self.store,
            url="https://example.com/category",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
        )
        Offer.objects.create(
            product=self.product,
            mapping_confirmed=True,
            store=self.store,
            watch_target=watch_target,
            title="Old title",
            url="https://example.com/product",
            availability=Offer.Availability.OUT_OF_STOCK,
        )
        mock_fetch_store_api.return_value = (
            [
                {
                    "name": "New title",
                    "slug": "pokemon-151-booster-bundle",
                    "permalink": "https://example.com/product",
                    "is_in_stock": False,
                    "prices": {"price": "1000", "currency_minor_unit": 2},
                }
            ],
            200,
        )

        check_watch_target(watch_target.id)

        offer = Offer.objects.get()
        self.assertEqual(offer.product, self.product)
        self.assertTrue(offer.mapping_confirmed)
        self.assertEqual(offer.title, "New title")

    @patch("monitor.scrapers.generic.GenericScraper.fetch")
    def test_product_page_maps_new_offer_to_target_product(self, mock_fetch):
        watch_target = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/product",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
        )
        mock_fetch.return_value = (
            "<html><head><title>Pokemon 151 Booster Bundle</title></head></html>",
            200,
        )

        check_watch_target(watch_target.id)

        offer = Offer.objects.get()
        self.assertEqual(offer.product, self.product)
        self.assertFalse(offer.mapping_confirmed)

    @patch("monitor.services.scraper_runner.notify_for_event")
    @patch("monitor.scrapers.generic.GenericScraper.fetch")
    def test_unchanged_in_stock_does_not_notify(self, mock_fetch, mock_notify):
        watch_target = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/in-stock",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
        )
        Offer.objects.create(
            product=self.product,
            store=self.store,
            watch_target=watch_target,
            title="Pokemon 151 Booster Bundle",
            url="https://example.com/in-stock",
            price=Decimal("10.00"),
            availability=Offer.Availability.IN_STOCK,
        )
        mock_fetch.return_value = (
            "<html><head><title>Pokemon 151 Booster Bundle</title></head><body></body></html>",
            200,
        )

        check_watch_target(watch_target.id)

        self.assertFalse(
            AvailabilityEvent.objects.filter(new_status=Offer.Availability.IN_STOCK).exists()
        )
        mock_notify.assert_not_called()

    @patch("monitor.scrapers.generic.GenericScraper.fetch", side_effect=RuntimeError("boom"))
    def test_failed_check_creates_failed_job_run(self, _mock_fetch):
        watch_target = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://example.com/fail",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
        )

        with self.assertRaises(RuntimeError):
            check_watch_target(watch_target.id)

        job_run = JobRun.objects.filter(status=JobRun.Status.FAILED).latest("created_at")
        self.assertIn("boom", job_run.error_message)


class GenericWooCommerceScraperTests(TestCase):
    def setUp(self) -> None:
        self.product = Product.objects.create(name="Pokemon Chaos Rising Booster Box")
        self.store = Store.objects.create(
            name="BattleStash",
            base_url="https://battlestash.pl",
            parser_type=Store.ParserType.GENERIC_WOOCOMMERCE,
        )
        self.watch_target = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
        )
        self.scraper = GenericWooCommerceScraper()

    @patch.object(GenericWooCommerceScraper, "fetch_store_api")
    def test_store_api_parses_minor_unit_price_and_stock(self, mock_fetch_store_api):
        mock_fetch_store_api.return_value = (
            [
                {
                    "id": 123,
                    "name": "Pokemon TCG Chaos Rising Booster Box",
                    "slug": "pokemon-tcg-chaos-rising-booster-box",
                    "permalink": self.watch_target.url,
                    "is_in_stock": True,
                    "prices": {
                        "price": "59999",
                        "currency_code": "PLN",
                        "currency_minor_unit": 2,
                    },
                }
            ],
            200,
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(offers[0].price, Decimal("599.99"))
        self.assertEqual(offers[0].availability, Offer.Availability.IN_STOCK)
        self.assertEqual(debug["source"], "woocommerce_store_api")

    @patch.object(GenericWooCommerceScraper, "fetch_store_api")
    def test_category_page_parses_all_store_api_products(self, mock_fetch_store_api):
        self.watch_target.product = None
        self.watch_target.mode = WatchTarget.Mode.CATEGORY_PAGE
        self.watch_target.url = "https://battlestash.pl/kategoria/pokemon-tcg/"
        self.watch_target.parser_config = {"api_params": {"category": "712"}}
        self.watch_target.save(
            update_fields=["product", "mode", "url", "parser_config", "updated_at"]
        )
        mock_fetch_store_api.return_value = (
            [
                {
                    "id": 123,
                    "name": "Pokemon TCG Chaos Rising Booster Box",
                    "slug": "pokemon-tcg-chaos-rising-booster-box",
                    "permalink": "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
                    "is_in_stock": True,
                    "prices": {"price": "59999", "currency_minor_unit": 2},
                },
                {
                    "id": 124,
                    "name": "Pokemon TCG Other Box",
                    "slug": "pokemon-tcg-other-box",
                    "permalink": "https://battlestash.pl/produkt/pokemon-tcg-other-box/",
                    "is_in_stock": False,
                    "prices": {"price": "19999", "currency_minor_unit": 2},
                },
            ],
            200,
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0].raw["product_id"], 123)
        self.assertEqual(offers[1].raw["slug"], "pokemon-tcg-other-box")
        self.assertEqual(debug["items_found"], 2)
        mock_fetch_store_api.assert_called_once_with(
            "https://battlestash.pl/wp-json/wc/store/v1/products",
            {"category": "712"},
        )

    @patch.object(GenericWooCommerceScraper, "fetch_product_page")
    @patch.object(GenericWooCommerceScraper, "fetch_store_api")
    def test_json_ld_fallback_parses_price_and_stock(
        self,
        mock_fetch_store_api,
        mock_fetch_product_page,
    ):
        mock_fetch_store_api.side_effect = WooCommerceScraperError("API blocked")
        mock_fetch_product_page.return_value = (
            """
            <script type="application/ld+json">
            {
              "@type": "Product",
              "name": "Pokemon TCG Chaos Rising Booster Box",
              "offers": {
                "@type": "Offer",
                "url": "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
                "price": "549.90",
                "priceCurrency": "PLN",
                "availability": "https://schema.org/OutOfStock"
              }
            }
            </script>
            """,
            200,
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(offers[0].price, Decimal("549.90"))
        self.assertEqual(offers[0].availability, Offer.Availability.OUT_OF_STOCK)
        self.assertEqual(debug["source"], "product_json_ld")

    @patch.object(GenericWooCommerceScraper, "fetch_product_page_pydoll")
    @patch.object(GenericWooCommerceScraper, "fetch_product_page")
    @patch.object(GenericWooCommerceScraper, "fetch_store_api")
    def test_pydoll_fallback_parses_json_ld(
        self,
        mock_fetch_store_api,
        mock_fetch_product_page,
        mock_fetch_product_page_pydoll,
    ):
        self.watch_target.parser_config = {"use_pydoll": True}
        self.watch_target.save(update_fields=["parser_config", "updated_at"])
        mock_fetch_store_api.side_effect = WooCommerceScraperError("API blocked")
        mock_fetch_product_page.side_effect = WooCommerceScraperError("Page blocked")
        mock_fetch_product_page_pydoll.return_value = (
            """
            <script type="application/ld+json">
            {
              "@type": "Product",
              "name": "Pokemon TCG Chaos Rising Booster Box",
              "offers": {
                "@type": "Offer",
                "price": "519.99",
                "priceCurrency": "PLN",
                "availability": "https://schema.org/InStock"
              }
            }
            </script>
            """,
            200,
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(offers[0].price, Decimal("519.99"))
        self.assertEqual(offers[0].availability, Offer.Availability.IN_STOCK)
        self.assertEqual(offers[0].raw["source"], "pydoll_product_json_ld")
        self.assertEqual(debug["source"], "pydoll_product_json_ld")

    def test_pydoll_options_use_persistent_profile_and_headed_chrome(self):
        self.watch_target.parser_config = {"pydoll_profile_dir": ".pydoll/test"}

        options = pydoll_options(self.watch_target)

        self.assertFalse(options.headless)
        self.assertTrue(
            any(argument.startswith("--user-data-dir=") for argument in options.arguments)
        )


class CloudflareApiReplayWooCommerceScraperTests(TestCase):
    def setUp(self) -> None:
        CloudflareApiReplayWooCommerceScraper._session_cache.clear()
        self.product = Product.objects.create(name="Pokemon Chaos Rising Booster Box")
        self.store = Store.objects.create(
            name="BattleStash",
            base_url="https://battlestash.pl",
            parser_type=Store.ParserType.CLOUDFLARE_API_REPLAY_WOOCOMMERCE,
        )
        self.watch_target = WatchTarget.objects.create(
            product=self.product,
            store=self.store,
            url="https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
            parser_config={
                "api_url": "https://battlestash.pl/wp-json/wc/store/products",
                "api_params": {"category": "712"},
                "product_slug": "pokemon-tcg-chaos-rising-booster-box",
            },
        )
        self.scraper = CloudflareApiReplayWooCommerceScraper()
        self.session = CloudflareBrowserSession(
            cookies=[
                {
                    "name": "cf_clearance",
                    "value": "clear",
                    "domain": ".battlestash.pl",
                    "path": "/",
                }
            ],
            request_headers=[
                {"name": "user-agent", "value": "Chrome"},
                {"name": "cookie", "value": "secret"},
                {"name": "accept", "value": "application/json"},
            ],
            metadata={"cookies_count": 1, "headers_count": 2},
        )

    def test_cookie_jar_and_replay_header_filtering(self):
        jar = build_cookie_jar(self.session.cookies)
        headers = replay_headers(self.session.request_headers)

        self.assertEqual(jar.get("cf_clearance"), "clear")
        self.assertEqual(headers["user-agent"], "Chrome")
        self.assertEqual(headers["accept"], "application/json")
        self.assertNotIn("cookie", headers)

    @patch.object(CloudflareApiReplayWooCommerceScraper, "fetch_api")
    @patch.object(CloudflareApiReplayWooCommerceScraper, "refresh_session")
    def test_api_json_parses_minor_unit_price_and_stock(
        self,
        mock_refresh_session,
        mock_fetch_api,
    ):
        mock_refresh_session.return_value = self.session
        mock_fetch_api.return_value = _json_response(
            [
                {
                    "id": 123,
                    "name": "Pokemon TCG Chaos Rising Booster Box",
                    "slug": "pokemon-tcg-chaos-rising-booster-box",
                    "permalink": "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
                    "is_in_stock": True,
                    "prices": {
                        "price": "59999",
                        "currency_code": "PLN",
                        "currency_minor_unit": 2,
                    },
                },
                {
                    "id": 124,
                    "name": "Other Product",
                    "slug": "other-product",
                    "is_in_stock": False,
                    "prices": {"price": "1000", "currency_minor_unit": 2},
                },
            ]
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].price, Decimal("599.99"))
        self.assertEqual(offers[0].availability, Offer.Availability.IN_STOCK)
        self.assertEqual(debug["source"], "cloudflare_api_replay_woocommerce")
        self.assertEqual(debug["items_found"], 1)
        self.watch_target.refresh_from_db()
        self.assertEqual(
            self.watch_target.parser_config["cloudflare_replay_session"]["cookies"][0]["value"],
            "clear",
        )

    @patch.object(CloudflareApiReplayWooCommerceScraper, "fetch_api")
    @patch.object(CloudflareApiReplayWooCommerceScraper, "refresh_session")
    def test_401_or_403_triggers_session_refresh_and_retry(
        self,
        mock_refresh_session,
        mock_fetch_api,
    ):
        refreshed_session = CloudflareBrowserSession(
            cookies=[{"name": "cf_clearance", "value": "new"}],
            request_headers=[{"name": "user-agent", "value": "Chrome"}],
            metadata={"cookies_count": 1},
        )
        mock_refresh_session.side_effect = [self.session, refreshed_session]
        mock_fetch_api.side_effect = [
            _text_response(403, "blocked", content_type="text/html"),
            _json_response(
                [
                    {
                        "id": 123,
                        "name": "Pokemon TCG Chaos Rising Booster Box",
                        "slug": "pokemon-tcg-chaos-rising-booster-box",
                        "is_in_stock": False,
                        "prices": {"price": "59999", "currency_minor_unit": 2},
                    }
                ]
            ),
        ]

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(mock_refresh_session.call_count, 2)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].availability, Offer.Availability.OUT_OF_STOCK)
        self.assertTrue(debug["refreshed"])
        self.assertEqual(debug["refresh_count"], 2)
        self.watch_target.refresh_from_db()
        self.assertEqual(
            self.watch_target.parser_config["cloudflare_replay_session"]["cookies"][0]["value"],
            "new",
        )

    @patch.object(CloudflareApiReplayWooCommerceScraper, "fetch_api")
    @patch.object(CloudflareApiReplayWooCommerceScraper, "refresh_session")
    def test_persisted_session_is_reused_without_refresh(
        self,
        mock_refresh_session,
        mock_fetch_api,
    ):
        self.watch_target.parser_config["cloudflare_replay_session"] = {
            "cookies": self.session.cookies,
            "request_headers": self.session.request_headers,
            "metadata": self.session.metadata,
        }
        self.watch_target.save(update_fields=["parser_config", "updated_at"])
        CloudflareApiReplayWooCommerceScraper._session_cache.clear()
        mock_fetch_api.return_value = _json_response(
            [
                {
                    "id": 123,
                    "name": "Pokemon TCG Chaos Rising Booster Box",
                    "slug": "pokemon-tcg-chaos-rising-booster-box",
                    "is_in_stock": True,
                    "prices": {"price": "59999", "currency_minor_unit": 2},
                }
            ]
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(len(offers), 1)
        self.assertFalse(debug["refreshed"])
        mock_refresh_session.assert_not_called()
        reused_session = mock_fetch_api.call_args.args[1]
        self.assertEqual(reused_session.cookies[0]["value"], "clear")

    @patch.object(CloudflareApiReplayWooCommerceScraper, "fetch_api")
    @patch.object(CloudflareApiReplayWooCommerceScraper, "refresh_session")
    def test_cloudflare_html_after_refresh_fails_without_fake_offer(
        self,
        mock_refresh_session,
        mock_fetch_api,
    ):
        mock_refresh_session.side_effect = [self.session, self.session]
        mock_fetch_api.side_effect = [
            _text_response(200, "<html>Just a moment...</html>", content_type="text/html"),
            _text_response(200, "<html>cf-chl-token</html>", content_type="text/html"),
        ]

        with self.assertRaises(CloudflareApiReplayWooCommerceError):
            self.scraper.parse_watch_target(self.watch_target)

    def test_registry_resolves_cloudflare_api_replay_parser(self):
        scraper = get_scraper(
            Store.ParserType.CLOUDFLARE_API_REPLAY_WOOCOMMERCE,
            timeout_seconds=15,
        )

        self.assertIsInstance(scraper, CloudflareApiReplayWooCommerceScraper)

    @patch.object(CloudflareApiReplayWooCommerceScraper, "fetch_api")
    @patch.object(CloudflareApiReplayWooCommerceScraper, "refresh_session")
    def test_without_product_slug_returns_all_api_products(
        self,
        mock_refresh_session,
        mock_fetch_api,
    ):
        self.watch_target.parser_config.pop("product_slug")
        self.watch_target.save(update_fields=["parser_config", "updated_at"])
        mock_refresh_session.return_value = self.session
        mock_fetch_api.return_value = _json_response(
            [
                {
                    "id": 123,
                    "name": "Pokemon TCG Chaos Rising Booster Box",
                    "slug": "pokemon-tcg-chaos-rising-booster-box",
                    "is_in_stock": True,
                    "prices": {"price": "59999", "currency_minor_unit": 2},
                },
                {
                    "id": 124,
                    "name": "Other Product",
                    "slug": "other-product",
                    "is_in_stock": False,
                    "prices": {"price": "1000", "currency_minor_unit": 2},
                },
            ]
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(len(offers), 2)
        self.assertEqual(debug["items_found"], 2)

    @patch.object(
        CloudflareApiReplayWooCommerceScraper,
        "refresh_session",
        side_effect=RuntimeError("challenge failed"),
    )
    def test_failed_refresh_creates_failed_job_run(self, _mock_refresh_session):
        with self.assertRaises(RuntimeError):
            check_watch_target(self.watch_target.id)

        job_run = JobRun.objects.filter(status=JobRun.Status.FAILED).latest("created_at")
        self.assertIn("challenge failed", job_run.error_message)


class AddWatchTargetCommandTests(TestCase):
    def test_product_page_requires_product_name(self):
        with self.assertRaises(CommandError):
            call_command(
                "add_watch_target",
                "BattleStash",
                "https://battlestash.pl",
                "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
                mode=WatchTarget.Mode.PRODUCT_PAGE,
            )

    def test_cloudflare_product_page_gets_default_replay_config_and_product(self):
        call_command(
            "add_watch_target",
            "BattleStash",
            "https://battlestash.pl",
            "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
            mode=WatchTarget.Mode.PRODUCT_PAGE,
            product_name="Pokemon Chaos Rising Booster Box",
            parser=Store.ParserType.CLOUDFLARE_API_REPLAY_WOOCOMMERCE,
        )

        watch_target = WatchTarget.objects.get(store__name="BattleStash")
        self.assertEqual(watch_target.product.name, "Pokemon Chaos Rising Booster Box")
        self.assertEqual(
            watch_target.parser_config["api_url"],
            "https://battlestash.pl/wp-json/wc/store/products",
        )
        self.assertEqual(
            watch_target.parser_config["browser_url"],
            "https://battlestash.pl/produkt/pokemon-tcg-chaos-rising-booster-box/",
        )
        self.assertEqual(
            watch_target.parser_config["product_slug"],
            "pokemon-tcg-chaos-rising-booster-box",
        )

    def test_category_cloudflare_parser_accepts_api_params_without_product_slug(self):
        call_command(
            "add_watch_target",
            "BattleStash",
            "https://battlestash.pl",
            "https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/",
            parser=Store.ParserType.CLOUDFLARE_API_REPLAY_WOOCOMMERCE,
            mode=WatchTarget.Mode.CATEGORY_PAGE,
            browser_url="https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/",
            api_param=["category=712", "orderby=date"],
            refresh_status_code=[401, 403],
        )

        watch_target = WatchTarget.objects.get(store__name="BattleStash")
        self.assertEqual(watch_target.mode, WatchTarget.Mode.CATEGORY_PAGE)
        self.assertIsNone(watch_target.product)
        self.assertEqual(
            watch_target.parser_config["browser_url"],
            "https://battlestash.pl/kategoria/gry-karciane/pokemon-tcg/",
        )
        self.assertEqual(
            watch_target.parser_config["api_params"],
            {"category": "712", "orderby": "date"},
        )
        self.assertEqual(watch_target.parser_config["refresh_status_codes"], [401, 403])
        self.assertNotIn("product_slug", watch_target.parser_config)

    def test_search_generic_woocommerce_persists_api_params_without_product(self):
        call_command(
            "add_watch_target",
            "BattleStash",
            "https://battlestash.pl",
            "https://battlestash.pl/?s=chaos",
            parser=Store.ParserType.GENERIC_WOOCOMMERCE,
            mode=WatchTarget.Mode.SEARCH_PAGE,
            api_param=["search=chaos", "per_page=100"],
        )

        watch_target = WatchTarget.objects.get(store__name="BattleStash")
        self.assertIsNone(watch_target.product)
        self.assertEqual(
            watch_target.parser_config["api_params"],
            {"search": "chaos", "per_page": "100"},
        )
        self.assertNotIn("product_slug", watch_target.parser_config)

    def test_category_shoper_parser_persists_api_params_without_product(self):
        call_command(
            "add_watch_target",
            "Strefa TCG",
            "https://strefa-tcg.pl",
            "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN",
            parser=Store.ParserType.SHOPER_FRONT_API,
            mode=WatchTarget.Mode.CATEGORY_PAGE,
            api_param=["limit=50", "sort=price"],
        )

        watch_target = WatchTarget.objects.get(store__name="Strefa TCG")
        self.assertIsNone(watch_target.product)
        self.assertEqual(watch_target.parser_config["api_params"], {"limit": "50", "sort": "price"})


class ShoperFrontApiScraperTests(TestCase):
    def setUp(self) -> None:
        self.store = Store.objects.create(
            name="Strefa TCG",
            base_url="https://strefa-tcg.pl",
            parser_type=Store.ParserType.SHOPER_FRONT_API,
        )
        self.watch_target = WatchTarget.objects.create(
            store=self.store,
            url="https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN",
            mode=WatchTarget.Mode.CATEGORY_PAGE,
        )
        self.scraper = ShoperFrontApiScraper()

    def test_registry_resolves_shoper_parser(self):
        scraper = get_scraper(Store.ParserType.SHOPER_FRONT_API, timeout_seconds=15)

        self.assertIsInstance(scraper, ShoperFrontApiScraper)

    def test_request_url_adds_default_limit(self):
        request_url = build_request_url(self.watch_target.url, {})

        self.assertEqual(
            request_url,
            "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN?limit=50",
        )

    def test_request_url_preserves_query_and_adds_limit(self):
        request_url = build_request_url(f"{self.watch_target.url}?sort=price", {})

        self.assertEqual(
            request_url,
            "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN?sort=price&limit=50",
        )

    def test_request_url_api_params_override_default_limit(self):
        request_url = build_request_url(self.watch_target.url, {"limit": "50", "sort": "name"})

        self.assertEqual(
            request_url,
            "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN?limit=50&sort=name",
        )

    @patch("monitor.scrapers.shoper_front_api.httpx.get")
    def test_list_response_parses_multiple_products(self, mock_get):
        mock_get.return_value = _shoper_response(
            [
                {
                    "id": 10,
                    "name": "Pokemon Box",
                    "url": "/pl/p/pokemon-box/10",
                    "price": {"gross": "129,99"},
                    "stock": 3,
                    "code": "BOX10",
                },
                {
                    "product_id": 11,
                    "title": "Sold Out Box",
                    "link": "https://strefa-tcg.pl/pl/p/sold-out-box/11",
                    "price_float": "99.50",
                    "buyable": False,
                    "sku": "BOX11",
                },
            ]
        )

        offers, debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0].title, "Pokemon Box")
        self.assertEqual(offers[0].url, "https://strefa-tcg.pl/pl/p/pokemon-box/10")
        self.assertEqual(offers[0].price, Decimal("129.99"))
        self.assertEqual(offers[0].currency, "PLN")
        self.assertEqual(offers[0].availability, Offer.Availability.IN_STOCK)
        self.assertEqual(offers[0].raw["product_id"], 10)
        self.assertEqual(offers[0].raw["code"], "BOX10")
        self.assertEqual(offers[1].availability, Offer.Availability.OUT_OF_STOCK)
        self.assertEqual(debug["items_found"], 2)
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN?limit=50",
        )

    @patch("monitor.scrapers.shoper_front_api.httpx.get")
    def test_dict_wrapped_response_and_fallback_url(self, mock_get):
        mock_get.return_value = _shoper_response(
            {
                "items": [
                    {
                        "id": 12,
                        "name": "Unknown Stock Box",
                        "price_value": "49.99",
                    }
                ]
            }
        )

        offers, _debug = self.scraper.parse_watch_target(self.watch_target)

        self.assertEqual(len(offers), 1)
        self.assertEqual(
            offers[0].url,
            "https://strefa-tcg.pl/webapi/front/pl_PL/products/PLN/12",
        )
        self.assertEqual(offers[0].availability, Offer.Availability.UNKNOWN)


class PydollBrowserTests(TestCase):
    def test_go_to_can_skip_full_page_load_wait(self):
        session = type("Session", (), {})()
        session.tab = type("Tab", (), {})()
        session.tab.go_to = AsyncMock()
        session.tab._execute_command = AsyncMock(return_value={"result": {}})

        asyncio.run(_go_to(session, "https://example.com", timeout=15, wait_for_page_load=False))

        session.tab.go_to.assert_not_called()
        session.tab._execute_command.assert_awaited_once()


def _json_response(payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "https://battlestash.pl/wp-json/wc/store/products"),
    )


def _text_response(
    status_code: int,
    text: str,
    content_type: str = "text/plain",
) -> httpx.Response:
    return httpx.Response(
        status_code,
        text=text,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://battlestash.pl/wp-json/wc/store/products"),
    )


def _shoper_response(payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request(
            "GET",
            "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN",
        ),
    )
