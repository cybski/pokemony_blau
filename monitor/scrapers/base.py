from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from monitor.models import WatchTarget


@dataclass(slots=True)
class ParsedOffer:
    title: str
    url: str
    price: Decimal | None
    currency: str
    availability: str
    raw: dict


class BaseScraper:
    parser_name = "base"

    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def parse_watch_target(self, watch_target: WatchTarget) -> tuple[list[ParsedOffer], dict]:
        raise NotImplementedError
