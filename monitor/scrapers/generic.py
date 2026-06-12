from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser

from monitor.models import Offer, WatchTarget
from monitor.scrapers.base import BaseScraper, ParsedOffer


class GenericScraper(BaseScraper):
    parser_name = "generic"

    def fetch(self, url: str) -> tuple[str, int]:
        response = httpx.get(
            url,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "pokemony-blau/0.1"},
        )
        response.raise_for_status()
        return response.text, response.status_code

    def parse_watch_target(self, watch_target: WatchTarget) -> tuple[list[ParsedOffer], dict]:
        html, http_status = self.fetch(watch_target.url)
        soup = BeautifulSoup(html, "html.parser")
        tree = HTMLParser(html)
        title = (soup.title.string.strip() if soup.title and soup.title.string else "") or (
            tree.css_first("title").text(strip=True) if tree.css_first("title") else watch_target.url
        )
        parsed_offer = ParsedOffer(
            title=title[:500],
            url=watch_target.url,
            price=None,
            currency="PLN",
            availability=Offer.Availability.UNKNOWN,
            raw={
                "final_url_host": urlparse(watch_target.url).netloc,
                "html_length": len(html),
                "page_title": title,
                "parser": self.parser_name,
            },
        )
        debug_payload = {
            "http_status": http_status,
            "parser": self.parser_name,
            "title": title,
            "html_length": len(html),
        }
        return [parsed_offer], debug_payload
