from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from monitor.models import AvailabilityEvent, JobRun, Offer, Product, Store, WatchTarget
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
    @patch("monitor.services.scraper_runner.GenericScraper.fetch")
    def test_offer_update_creates_availability_event(self, mock_fetch, mock_notify):
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
    @patch("monitor.services.scraper_runner.GenericScraper.fetch")
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

    @patch("monitor.services.scraper_runner.GenericScraper.fetch", side_effect=RuntimeError("boom"))
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
