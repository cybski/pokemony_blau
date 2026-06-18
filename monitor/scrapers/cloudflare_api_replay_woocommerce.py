from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from monitor.models import Offer, WatchTarget
from monitor.scrapers.base import BaseScraper, ParsedOffer
from monitor.scrapers.pydoll_browser import (
    CloudflareBrowserSession,
    CHALLENGE_MARKERS,
    refresh_cloudflare_api_session,
)


EXCLUDED_REPLAY_HEADERS = {
    "accept-encoding",
    "connection",
    "content-length",
    "cookie",
    "host",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class CloudflareApiReplayWooCommerceError(RuntimeError):
    pass


@dataclass(slots=True)
class ApiFetchResult:
    products: list[dict[str, Any]]
    status_code: int
    refreshed: bool
    refresh_count: int
    attempts: list[dict[str, Any]]
    session_metadata: dict[str, Any]


class CloudflareApiReplayWooCommerceScraper(BaseScraper):
    parser_name = "cloudflare_api_replay_woocommerce"
    _session_cache: dict[tuple[int, str, str], CloudflareBrowserSession] = {}

    def parse_watch_target(self, watch_target: WatchTarget) -> tuple[list[ParsedOffer], dict]:
        result = self.fetch_products(watch_target)
        products = self.filter_products(result.products, watch_target)
        parsed_offers = [
            self._parse_api_product(product, watch_target) for product in products
        ]
        return parsed_offers, {
            "http_status": result.status_code,
            "parser": self.parser_name,
            "source": "cloudflare_api_replay_woocommerce",
            "items_found": len(parsed_offers),
            "refreshed": result.refreshed,
            "refresh_count": result.refresh_count,
            "attempts": result.attempts,
            "session": result.session_metadata,
        }

    def fetch_products(self, watch_target: WatchTarget) -> ApiFetchResult:
        config = watch_target.parser_config
        api_url = str(config.get("api_url") or "")
        if not api_url:
            raise CloudflareApiReplayWooCommerceError(
                "parser_config.api_url is required."
            )
        api_params = config.get("api_params") or {}
        request_url = _api_url_with_params(api_url, api_params)
        refresh_status_codes = _refresh_status_codes(config)
        cache_key = (
            watch_target.store_id,
            str(config.get("pydoll_profile_dir") or f".pydoll/{watch_target.store_id}"),
            request_url,
        )
        session = self._session_cache.get(cache_key)
        refresh_count = 0
        attempts: list[dict[str, Any]] = []
        refreshed = False

        if session is None:
            session = self.refresh_session(watch_target, request_url)
            self._session_cache[cache_key] = session
            refresh_count += 1
            refreshed = True

        response = self.fetch_api(request_url, session)
        attempts.append(_attempt_debug(response, "httpx_api", refresh_status_codes))

        if _needs_refresh(response, refresh_status_codes):
            session = self.refresh_session(watch_target, request_url)
            self._session_cache[cache_key] = session
            refresh_count += 1
            refreshed = True
            response = self.fetch_api(request_url, session)
            attempts.append(
                _attempt_debug(
                    response,
                    "httpx_api_after_refresh",
                    refresh_status_codes,
                )
            )

        if _needs_refresh(response, refresh_status_codes):
            raise CloudflareApiReplayWooCommerceError(
                f"API remained blocked after browser refresh: HTTP {response.status_code}."
            )

        response.raise_for_status()
        products = _products_from_response(response)
        return ApiFetchResult(
            products=products,
            status_code=response.status_code,
            refreshed=refreshed,
            refresh_count=refresh_count,
            attempts=attempts,
            session_metadata=session.metadata,
        )

    def refresh_session(
        self,
        watch_target: WatchTarget,
        api_url: str,
    ) -> CloudflareBrowserSession:
        return refresh_cloudflare_api_session(watch_target, api_url=api_url)

    def fetch_api(
        self,
        api_url: str,
        session: CloudflareBrowserSession,
    ) -> httpx.Response:
        return httpx.get(
            api_url,
            cookies=build_cookie_jar(session.cookies),
            headers=replay_headers(session.request_headers),
            follow_redirects=True,
            timeout=self.timeout_seconds,
        )

    def filter_products(
        self,
        products: list[dict[str, Any]],
        watch_target: WatchTarget,
    ) -> list[dict[str, Any]]:
        product_slug = watch_target.parser_config.get("product_slug")
        if not product_slug:
            return products
        return [
            product
            for product in products
            if str(product.get("slug") or "") == str(product_slug)
        ]

    def _parse_api_product(
        self,
        product: dict[str, Any],
        watch_target: WatchTarget,
    ) -> ParsedOffer:
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
            url=str(product.get("permalink") or product.get("url") or watch_target.url),
            price=price,
            currency=str(prices.get("currency_code") or "PLN"),
            availability=availability,
            raw={
                "source": "cloudflare_api_replay_woocommerce",
                "product_id": product.get("id"),
                "slug": product.get("slug"),
                "is_in_stock": product.get("is_in_stock"),
                "prices": prices,
            },
        )


def build_cookie_jar(cookies: list[dict[str, Any]]) -> httpx.Cookies:
    jar = httpx.Cookies()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        jar.set(
            str(name),
            str(value),
            domain=cookie.get("domain") or None,
            path=str(cookie.get("path") or "/"),
        )
    return jar


def replay_headers(headers: list[dict[str, str]]) -> dict[str, str]:
    return {
        str(header["name"]): str(header["value"])
        for header in headers
        if header.get("name")
        and not str(header["name"]).startswith(":")
        and str(header["name"]).lower() not in EXCLUDED_REPLAY_HEADERS
    }


def _refresh_status_codes(config: dict[str, Any]) -> set[int]:
    configured = config.get("refresh_status_codes", [401, 403])
    try:
        return {int(status_code) for status_code in configured}
    except (TypeError, ValueError) as exc:
        raise CloudflareApiReplayWooCommerceError(
            "parser_config.refresh_status_codes must be a list of integers."
        ) from exc


def _api_url_with_params(api_url: str, params: dict[str, Any]) -> str:
    if not params:
        return api_url
    return str(httpx.URL(api_url).copy_merge_params(params))


def _needs_refresh(response: httpx.Response, refresh_status_codes: set[int]) -> bool:
    if response.status_code in refresh_status_codes:
        return True
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    content_type = response.headers.get("content-type", "")
    return "html" in content_type.lower() and _is_challenge_text(response.text)


def _is_challenge_text(text: str) -> bool:
    beginning = text[:5000].lower()
    return any(marker in beginning for marker in CHALLENGE_MARKERS)


def _attempt_debug(
    response: httpx.Response,
    source: str,
    refresh_status_codes: set[int],
) -> dict[str, Any]:
    return {
        "source": source,
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "blocked": _needs_refresh(response, refresh_status_codes),
    }


def _products_from_response(response: httpx.Response) -> list[dict[str, Any]]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise CloudflareApiReplayWooCommerceError(
            "API response was not valid JSON."
        ) from exc

    if isinstance(payload, list):
        products = payload
    elif isinstance(payload, dict) and isinstance(payload.get("products"), list):
        products = payload["products"]
    else:
        raise CloudflareApiReplayWooCommerceError(
            "WooCommerce API returned a non-list response."
        )

    if not all(isinstance(product, dict) for product in products):
        raise CloudflareApiReplayWooCommerceError(
            "WooCommerce API returned invalid product rows."
        )
    return products


def _minor_unit_price(value: Any, minor_unit: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).scaleb(-int(minor_unit or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CloudflareApiReplayWooCommerceError(
            f"Invalid WooCommerce price: {value!r}"
        ) from exc
