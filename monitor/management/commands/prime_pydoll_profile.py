import asyncio

from django.core.management.base import BaseCommand, CommandError
from pydoll.exceptions import PydollException

from monitor.models import WatchTarget
from monitor.scrapers.generic_woocommerce import _is_challenge_html
from monitor.scrapers.pydoll_browser import (
    pydoll_profile_dir,
    start_pydoll_session,
)


class Command(BaseCommand):
    help = "Open headed Chrome with Pydoll to establish a persistent browser profile."

    def add_arguments(self, parser):
        parser.add_argument("watch_target_id", type=int)

    def handle(self, *args, **options):
        watch_target = WatchTarget.objects.select_related("store").get(
            pk=options["watch_target_id"]
        )
        config = watch_target.parser_config
        config.update(
            {
                "use_pydoll": True,
                "pydoll_headless": False,
                "pydoll_keep_open": False,
            }
        )
        watch_target.parser_config = config

        profile_dir = pydoll_profile_dir(watch_target)
        self.stdout.write(f"Opening {watch_target.url}")
        self.stdout.write(f"Persistent profile: {profile_dir.resolve()}")
        self.stdout.write("Complete any browser challenge, then return here and press Enter.")

        try:
            asyncio.run(self._prime(watch_target))
        except PydollException as exc:
            raise CommandError(f"Pydoll failed: {exc}") from exc

        config["pydoll_profile_dir"] = str(profile_dir)
        watch_target.parser_config = config
        watch_target.save(update_fields=["parser_config", "updated_at"])
        self.stdout.write(self.style.SUCCESS("Pydoll profile primed and fallback enabled."))

    async def _prime(self, watch_target: WatchTarget) -> None:
        session = await start_pydoll_session(watch_target)
        try:
            await session.tab.go_to(
                watch_target.url,
                timeout=watch_target.store.timeout_seconds,
            )
            await asyncio.to_thread(input)
            html = await session.tab.page_source
            if _is_challenge_html(html):
                raise CommandError(
                    "Cloudflare challenge is still active. "
                    "The browser profile was not marked as primed."
                )
        finally:
            await session.browser.stop()
