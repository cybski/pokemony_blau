from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple

from monitor.jobs import enqueue_watch_target_check
from monitor.models import (
    AvailabilityEvent,
    JobRun,
    Notification,
    Offer,
    Product,
    Store,
    WatchTarget,
)


class OfferMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Offer) -> str:
        return f"{obj.store.name}: {obj.title} ({obj.availability})"


class ProductAdminForm(forms.ModelForm):
    offers = OfferMultipleChoiceField(
        queryset=Offer.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("offers", is_stacked=False),
        help_text=(
            "Select offers linked to this product. "
            "Use the filter box above the available offers list to search by text."
        ),
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["offers"].queryset = Offer.objects.select_related("store").order_by(
            "store__name",
            "title",
        )
        if self.instance.pk:
            self.fields["offers"].initial = self.instance.offers.all()

    def _save_m2m(self):
        super()._save_m2m()
        if not self.instance.pk:
            return

        selected_offers = self.cleaned_data["offers"]
        selected_offer_ids = selected_offers.values_list("id", flat=True)
        self.instance.offers.exclude(id__in=selected_offer_ids).update(
            product=None,
            mapping_confirmed=False,
        )
        selected_offers.update(product=self.instance, mapping_confirmed=True)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "is_active", "updated_at")
    search_fields = ("name", "notes")
    list_filter = ("is_active",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "parser_type",
        "is_active",
        "rate_limit_seconds",
        "timeout_seconds",
        "updated_at",
    )
    search_fields = ("name", "base_url", "notes")
    list_filter = ("is_active", "parser_type")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.action(description="Activate selected watch targets")
def activate_watch_targets(modeladmin, request, queryset):
    count = queryset.update(is_active=True)
    modeladmin.message_user(request, f"Activated {count} watch targets.", messages.SUCCESS)


@admin.action(description="Deactivate selected watch targets")
def deactivate_watch_targets(modeladmin, request, queryset):
    count = queryset.update(is_active=False)
    modeladmin.message_user(request, f"Deactivated {count} watch targets.", messages.SUCCESS)


@admin.action(description="Enqueue selected watch targets for checking")
def enqueue_watch_targets(modeladmin, request, queryset):
    count = 0
    for watch_target in queryset:
        enqueue_watch_target_check(watch_target.id)
        count += 1
    modeladmin.message_user(request, f"Enqueued {count} watch targets.", messages.SUCCESS)


@admin.register(WatchTarget)
class WatchTargetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "store",
        "mode",
        "is_active",
        "poll_interval_seconds",
        "next_check_at",
        "last_checked_at",
    )
    search_fields = ("url", "notes", "product__name", "store__name")
    list_filter = ("is_active", "mode", "store")
    ordering = ("next_check_at", "id")
    readonly_fields = ("created_at", "updated_at", "last_checked_at", "next_check_at")
    actions = (activate_watch_targets, deactivate_watch_targets, enqueue_watch_targets)


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "store",
        "product",
        "mapping_confirmed",
        "availability",
        "price",
        "currency",
        "last_seen_at",
        "last_changed_at",
    )
    list_editable = ("product", "mapping_confirmed")
    search_fields = (
        "title",
        "url",
        "product__name",
        "store__name",
        "raw__slug",
        "raw__product_id",
    )
    list_filter = (
        ("product", admin.EmptyFieldListFilter),
        "mapping_confirmed",
        "availability",
        "currency",
        "store",
    )
    ordering = ("-last_seen_at",)
    readonly_fields = ("created_at", "updated_at", "last_seen_at", "last_changed_at")


@admin.register(AvailabilityEvent)
class AvailabilityEventAdmin(admin.ModelAdmin):
    list_display = (
        "offer",
        "event_type",
        "previous_status",
        "new_status",
        "previous_price",
        "new_price",
        "detected_at",
    )
    search_fields = ("offer__title", "offer__url")
    list_filter = ("event_type", "new_status", "previous_status")
    ordering = ("-detected_at",)
    readonly_fields = ("created_at", "detected_at")


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "store",
        "watch_target",
        "http_status",
        "items_found",
        "parser_name",
        "created_at",
    )
    search_fields = ("error_message", "parser_name", "watch_target__url", "store__name")
    list_filter = ("status", "parser_name", "store")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "started_at", "finished_at", "debug_payload")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "channel",
        "status",
        "destination",
        "sent_at",
        "created_at",
    )
    search_fields = ("destination", "payload_summary", "error_message")
    list_filter = ("channel", "status")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "sent_at")
