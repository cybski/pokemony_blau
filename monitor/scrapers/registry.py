from __future__ import annotations

from monitor.models import Store
from monitor.scrapers.base import BaseScraper
from monitor.scrapers.cloudflare_api_replay_woocommerce import (
    CloudflareApiReplayWooCommerceScraper,
)
from monitor.scrapers.generic import GenericScraper
from monitor.scrapers.generic_woocommerce import GenericWooCommerceScraper


SCRAPERS: dict[str, type[BaseScraper]] = {
    Store.ParserType.GENERIC: GenericScraper,
    Store.ParserType.GENERIC_WOOCOMMERCE: GenericWooCommerceScraper,
    Store.ParserType.CLOUDFLARE_API_REPLAY_WOOCOMMERCE: (
        CloudflareApiReplayWooCommerceScraper
    ),
}


def get_scraper(parser_type: str, timeout_seconds: int) -> BaseScraper:
    try:
        scraper_class = SCRAPERS[parser_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported parser type: {parser_type}") from exc
    return scraper_class(timeout_seconds=timeout_seconds)
