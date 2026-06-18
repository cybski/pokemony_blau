from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydoll.exceptions import PydollException

from monitor.models import Offer, WatchTarget
from monitor.scrapers.base import BaseScraper, ParsedOffer
from monitor.scrapers.pydoll_browser import fetch_product_page_pydoll


class WooCommerceScraperError(RuntimeError):
    pass


class GenericWooCommerceScraper(BaseScraper):
    parser_name = "generic_woocommerce"

    def parse_watch_target(self, watch_target: WatchTarget) -> tuple[list[ParsedOffer], dict]:
        config = watch_target.parser_config
        api_url = config.get("store_api_url") or (
            f"{watch_target.store.base_url.rstrip('/')}/wp-json/wc/store/v1/products"
        )
        attempts: list[dict] = []
        is_listing_target = watch_target.mode in (
            WatchTarget.Mode.CATEGORY_PAGE,
            WatchTarget.Mode.SEARCH_PAGE,
        )

        if is_listing_target:
            products, status_code = self.fetch_store_api(
                api_url,
                config.get("api_params") or {},
            )
            return [self._parse_api_product(product, watch_target) for product in products], {
                "http_status": status_code,
                "parser": self.parser_name,
                "source": "woocommerce_store_api",
                "items_found": len(products),
            }

        slug = config.get("product_slug") or _product_slug(watch_target.url)

        if config.get("use_store_api", True):
            try:
                products, status_code = self.fetch_store_api(api_url, {"slug": slug})
                attempts.append(
                    {
                        "source": "woocommerce_store_api",
                        "http_status": status_code,
                        "items_found": len(products),
                    }
                )
                if products:
                    return [self._parse_api_product(products[0], watch_target)], {
                        "http_status": status_code,
                        "parser": self.parser_name,
                        "source": "woocommerce_store_api",
                        "attempts": attempts,
                    }
            except (httpx.HTTPError, ValueError, WooCommerceScraperError) as exc:
                attempts.append(
                    {
                        "source": "woocommerce_store_api",
                        "error": str(exc),
                    }
                )

        try:
            html, status_code = self.fetch_product_page(watch_target.url)
            parsed_offer = self._parse_json_ld(html, watch_target)
            attempts.append(
                {
                    "source": "product_json_ld",
                    "http_status": status_code,
                    "items_found": 1,
                }
            )
            return [parsed_offer], {
                "http_status": status_code,
                "parser": self.parser_name,
                "source": "product_json_ld",
                "attempts": attempts,
            }
        except (httpx.HTTPError, ValueError, WooCommerceScraperError) as exc:
            attempts.append({"source": "product_json_ld", "error": str(exc)})

        if config.get("use_pydoll", False):
            try:
                html, status_code = self.fetch_product_page_pydoll(watch_target)
                parsed_offer = self._parse_json_ld(html, watch_target)
                parsed_offer.raw["source"] = "pydoll_product_json_ld"
                attempts.append(
                    {
                        "source": "pydoll_product_json_ld",
                        "http_status": status_code,
                        "items_found": 1,
                    }
                )
                return [parsed_offer], {
                    "http_status": status_code,
                    "parser": self.parser_name,
                    "source": "pydoll_product_json_ld",
                    "attempts": attempts,
                }
            except (PydollException, ValueError, WooCommerceScraperError) as exc:
                attempts.append(
                    {
                        "source": "pydoll_product_json_ld",
                        "error": str(exc),
                    }
                )

        raise WooCommerceScraperError(
            "All configured WooCommerce fetch methods failed. "
            f"Attempts: {attempts}"
        )

    def fetch_store_api(self, api_url: str, params: dict) -> tuple[list[dict], int]:
        response = httpx.get(
            api_url,
            params=params,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=_headers(),
        )
        _raise_for_challenge(response)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise WooCommerceScraperError("Store API returned a non-list response.")
        return data, response.status_code

    def fetch_product_page(self, url: str) -> tuple[str, int]:
        response = httpx.get(
            url,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=_headers(),
        )
        _raise_for_challenge(response)
        response.raise_for_status()
        return response.text, response.status_code

    def fetch_product_page_pydoll(self, watch_target: WatchTarget) -> tuple[str, int]:
        html, status_code = fetch_product_page_pydoll(watch_target)
        if _is_challenge_html(html):
            raise WooCommerceScraperError(
                "Cloudflare challenge remained after Pydoll navigation. "
                "Complete it in the open Chrome window."
            )
        return html, status_code

    def _parse_api_product(self, product: dict, watch_target: WatchTarget) -> ParsedOffer:
        prices = product.get("prices") or {}
        price = _minor_unit_price(prices.get("price"), prices.get("currency_minor_unit"))
        availability = (
            Offer.Availability.IN_STOCK
            if product.get("is_in_stock") is True
            else Offer.Availability.OUT_OF_STOCK
            if product.get("is_in_stock") is False
            else Offer.Availability.UNKNOWN
        )
        return ParsedOffer(
            title=str(product.get("name") or watch_target.url)[:500],
            url=str(product.get("permalink") or watch_target.url),
            price=price,
            currency=str(prices.get("currency_code") or "PLN"),
            availability=availability,
            raw={
                "source": "woocommerce_store_api",
                "product_id": product.get("id"),
                "slug": product.get("slug"),
                "is_in_stock": product.get("is_in_stock"),
                "prices": prices,
            },
        )

    def _parse_json_ld(self, html: str, watch_target: WatchTarget) -> ParsedOffer:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue

            for item in _walk_json_ld(payload):
                if _has_type(item, "Product"):
                    return _parsed_offer_from_json_ld(item, watch_target)

        raise WooCommerceScraperError("No Product JSON-LD found on product page.")


def _product_slug(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if not path_parts:
        raise WooCommerceScraperError("Could not derive a product slug from the watch URL.")
    return path_parts[-1]


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/html;q=0.9",
        "User-Agent": "pokemony-blau/0.1 (+private availability monitor)",
    }


def _raise_for_challenge(response: httpx.Response) -> None:
    if response.headers.get("cf-mitigated") == "challenge":
        raise WooCommerceScraperError("Cloudflare challenge blocked the request.")
    if _is_challenge_html(response.text):
        raise WooCommerceScraperError("Cloudflare challenge blocked the request.")


def _is_challenge_html(html: str) -> bool:
    beginning = html[:5000]
    return "Just a moment..." in beginning or "cf-chl-" in beginning


def _minor_unit_price(value, minor_unit) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).scaleb(-int(minor_unit or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise WooCommerceScraperError(f"Invalid WooCommerce price: {value!r}") from exc


def _walk_json_ld(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json_ld(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_ld(child)


def _has_type(item: dict, expected: str) -> bool:
    item_type = item.get("@type")
    return item_type == expected or (
        isinstance(item_type, list) and expected in item_type
    )


def _parsed_offer_from_json_ld(item: dict, watch_target: WatchTarget) -> ParsedOffer:
    offers = item.get("offers")
    if isinstance(offers, list):
        offer = offers[0] if offers else {}
    elif isinstance(offers, dict):
        offer = offers
    else:
        offer = {}

    price_value = offer.get("price") or offer.get("lowPrice")
    try:
        price = Decimal(str(price_value)) if price_value not in (None, "") else None
    except InvalidOperation as exc:
        raise WooCommerceScraperError(f"Invalid JSON-LD price: {price_value!r}") from exc

    availability_url = str(offer.get("availability") or "")
    availability_name = availability_url.rsplit("/", 1)[-1].lower()
    availability = {
        "instock": Offer.Availability.IN_STOCK,
        "limitedavailability": Offer.Availability.IN_STOCK,
        "preorder": Offer.Availability.PREORDER,
        "presale": Offer.Availability.PREORDER,
        "outofstock": Offer.Availability.OUT_OF_STOCK,
        "soldout": Offer.Availability.OUT_OF_STOCK,
        "discontinued": Offer.Availability.MISSING,
    }.get(availability_name, Offer.Availability.UNKNOWN)

    return ParsedOffer(
        title=str(item.get("name") or watch_target.url)[:500],
        url=str(offer.get("url") or item.get("url") or watch_target.url),
        price=price,
        currency=str(offer.get("priceCurrency") or "PLN"),
        availability=availability,
        raw={
            "source": "product_json_ld",
            "product": item,
        },
    )
