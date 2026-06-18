from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Product(TimestampedModel):
    name = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Store(TimestampedModel):
    class ParserType(models.TextChoices):
        GENERIC = "generic", "Generic"
        GENERIC_WOOCOMMERCE = "generic_woocommerce", "Generic WooCommerce"
        CLOUDFLARE_API_REPLAY_WOOCOMMERCE = (
            "cloudflare_api_replay_woocommerce",
            "Cloudflare API replay WooCommerce",
        )

    name = models.CharField(max_length=255)
    base_url = models.URLField()
    parser_type = models.CharField(
        max_length=50,
        choices=ParserType.choices,
        default=ParserType.GENERIC,
    )
    is_active = models.BooleanField(default=True)
    rate_limit_seconds = models.PositiveIntegerField(default=5)
    timeout_seconds = models.PositiveIntegerField(default=15)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WatchTarget(TimestampedModel):
    class Mode(models.TextChoices):
        PRODUCT_PAGE = "product_page", "Product page"
        SEARCH_PAGE = "search_page", "Search page"
        CATEGORY_PAGE = "category_page", "Category page"

    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="watch_targets",
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="watch_targets",
    )
    url = models.URLField()
    mode = models.CharField(max_length=32, choices=Mode.choices)
    is_active = models.BooleanField(default=True)
    poll_interval_seconds = models.PositiveIntegerField(default=300)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(default=timezone.now)
    parser_config = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["next_check_at", "id"]

    def __str__(self) -> str:
        return f"{self.store.name}: {self.url}"


class Offer(TimestampedModel):
    class Availability(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        MISSING = "missing", "Missing"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"
        IN_STOCK = "in_stock", "In stock"
        PREORDER = "preorder", "Preorder"

    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offers",
    )
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="offers")
    watch_target = models.ForeignKey(
        WatchTarget,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    title = models.CharField(max_length=500)
    url = models.URLField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="PLN")
    availability = models.CharField(
        max_length=32,
        choices=Availability.choices,
        default=Availability.UNKNOWN,
    )
    raw = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "watch_target", "url"],
                name="unique_offer_per_watch_target_url",
            )
        ]

    def __str__(self) -> str:
        return self.title


class AvailabilityEvent(models.Model):
    class EventType(models.TextChoices):
        AVAILABILITY_CHANGED = "availability_changed", "Availability changed"
        PRICE_CHANGED = "price_changed", "Price changed"
        FOUND = "found", "Found"
        DISAPPEARED = "disappeared", "Disappeared"

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="events")
    previous_status = models.CharField(max_length=32, blank=True)
    new_status = models.CharField(max_length=32, blank=True)
    previous_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    new_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    detected_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_at", "-id"]

    def __str__(self) -> str:
        return f"{self.offer} {self.event_type}"


class JobRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        PARTIAL = "partial", "Partial"

    store = models.ForeignKey(
        Store,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_runs",
    )
    watch_target = models.ForeignKey(
        WatchTarget,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_runs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    http_status = models.PositiveIntegerField(null=True, blank=True)
    items_found = models.PositiveIntegerField(default=0)
    parser_name = models.CharField(max_length=255, blank=True)
    debug_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"JobRun #{self.pk} {self.status}"


class Notification(models.Model):
    class Channel(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        DISCORD = "discord", "Discord"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    event = models.ForeignKey(
        AvailabilityEvent,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    channel = models.CharField(max_length=16, choices=Channel.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    destination = models.CharField(max_length=500, blank=True)
    payload_summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.channel} {self.status}"
