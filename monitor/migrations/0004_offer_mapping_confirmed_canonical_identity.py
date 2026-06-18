from django.db import migrations, models
from django.db.models import Count


def deduplicate_store_url_offers(apps, schema_editor):
    Offer = apps.get_model("monitor", "Offer")
    AvailabilityEvent = apps.get_model("monitor", "AvailabilityEvent")

    duplicate_keys = (
        Offer.objects.values("store_id", "url")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
    )
    for duplicate_key in duplicate_keys:
        offers = list(
            Offer.objects.filter(
                store_id=duplicate_key["store_id"],
                url=duplicate_key["url"],
            ).order_by("-last_seen_at", "-id")
        )
        keeper = offers[0]
        for duplicate in offers[1:]:
            AvailabilityEvent.objects.filter(offer=duplicate).update(offer=keeper)
            if keeper.product_id is None and duplicate.product_id is not None:
                keeper.product_id = duplicate.product_id
            if duplicate.mapping_confirmed:
                keeper.mapping_confirmed = True
            duplicate.delete()
        keeper.save(update_fields=["product", "mapping_confirmed", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0003_add_cloudflare_api_replay_parser_type"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="offer",
            name="unique_offer_per_watch_target_url",
        ),
        migrations.AddField(
            model_name="offer",
            name="mapping_confirmed",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(deduplicate_store_url_offers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="offer",
            constraint=models.UniqueConstraint(
                fields=("store", "url"),
                name="unique_offer_per_store_url",
            ),
        ),
    ]
