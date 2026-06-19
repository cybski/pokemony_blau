from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from monitor.models import Offer, WatchTarget
from monitor.scrapers.base import BaseScraper, ParsedOffer


class ShoperFrontApiError(RuntimeError):
    pass


class ShoperFrontApiScraper(BaseScraper):
    parser_name = "shoper_front_api"

    def parse_watch_target(self, watch_target: WatchTarget) -> tuple[list[ParsedOffer], dict]:
        request_url = build_request_url(
            watch_target.url,
            watch_target.parser_config.get("api_params") or {},
        )
        products, status_code = self.fetch_products(request_url)
        offers = [
            parse_product(product, watch_target, index)
            for index, product in enumerate(products)
        ]
        return offers, {
            "http_status": status_code,
            "parser": self.parser_name,
            "source": self.parser_name,
            "items_found": len(offers),
            "request_url": request_url,
        }

    def fetch_products(self, request_url: str) -> tuple[list[dict[str, Any]], int]:
        response = httpx.get(
            request_url,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "pokemony-blau/0.1 (+private availability monitor)",
            },
        )
        response.raise_for_status()
        return products_from_payload(response.json()), response.status_code


def build_request_url(url: str, api_params: dict[str, Any]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "limit" not in query and "limit" not in api_params:
        query["limit"] = "50"
    query.update({str(key): str(value) for key, value in api_params.items()})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def products_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        products = payload
    elif isinstance(payload, dict):
        products = _first_list(payload, ("products", "items", "list", "data"))
    else:
        products = None

    if products is None:
        raise ShoperFrontApiError("Shoper Front API returned no product list.")
    if not all(isinstance(product, dict) for product in products):
        raise ShoperFrontApiError("Shoper Front API returned invalid product rows.")
    return products


def parse_product(product: dict[str, Any], watch_target: WatchTarget, index: int) -> ParsedOffer:
    product_id = _first_present(product, ("id", "product_id", "productId"))
    code = _first_present(product, ("code", "sku", "symbol"))
    return ParsedOffer(
        title=str(_first_present(product, ("name", "title", "product_name")) or watch_target.url)[
            :500
        ],
        url=_product_url(product, watch_target, product_id, index),
        price=_product_price(product),
        currency=_currency_from_url(watch_target.url),
        availability=_product_availability(product),
        raw={
            "source": "shoper_front_api",
            "product_id": product_id,
            "code": code,
            "sku": code,
            "product": product,
        },
    )


def _product_url(
    product: dict[str, Any],
    watch_target: WatchTarget,
    product_id: Any,
    index: int,
) -> str:
    value = _first_present(product, ("url", "link", "absolute_url", "product_url"))
    if value:
        value = str(value)
        return value if value.startswith(("http://", "https://")) else urljoin(
            watch_target.store.base_url,
            value,
        )

    if product_id not in (None, ""):
        lang = _lang_from_url(watch_target.url)
        currency = _currency_from_url(watch_target.url)
        return (
            f"{watch_target.store.base_url.rstrip('/')}/webapi/front/"
            f"{lang}/products/{currency}/{product_id}"
        )
    return f"{watch_target.url}#product-{index}"


def _product_price(product: dict[str, Any]) -> Decimal | None:
    for value in (
        product.get("price"),
        product.get("price_float"),
        product.get("price_value"),
        _nested(product, ("price", "gross")),
        _nested(product, ("price", "final")),
    ):
        price = _to_decimal(value)
        if price is not None:
            return price
    return None


def _product_availability(product: dict[str, Any]) -> str:
    for key in ("stock", "stock_quantity", "quantity", "amount"):
        if key in product:
            quantity = _to_decimal(product[key])
            if quantity is not None:
                return (
                    Offer.Availability.IN_STOCK
                    if quantity > 0
                    else Offer.Availability.OUT_OF_STOCK
                )

    for key in ("available", "availability", "buyable", "can_buy", "is_available"):
        if key not in product:
            continue
        value = product[key]
        if isinstance(value, bool):
            return Offer.Availability.IN_STOCK if value else Offer.Availability.OUT_OF_STOCK
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "available", "in_stock", "instock"}:
            return Offer.Availability.IN_STOCK
        if normalized in {"0", "false", "no", "unavailable", "out_of_stock", "outofstock"}:
            return Offer.Availability.OUT_OF_STOCK

    return Offer.Availability.UNKNOWN


def _first_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _first_present(product: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = product.get(key)
        if value not in (None, ""):
            return value
    return None


def _nested(product: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = product
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, dict):
        return None
    text = str(value).strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _lang_from_url(url: str) -> str:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    try:
        return parts[parts.index("front") + 1]
    except (ValueError, IndexError):
        return "pl_PL"


def _currency_from_url(url: str) -> str:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    try:
        return parts[parts.index("products") + 1]
    except (ValueError, IndexError):
        return "PLN"
