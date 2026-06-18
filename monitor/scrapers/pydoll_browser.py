from __future__ import annotations

import asyncio
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

from monitor.models import WatchTarget


@dataclass
class PydollSession:
    browser: Chrome
    tab: object


@dataclass(slots=True)
class CloudflareBrowserSession:
    cookies: list[dict[str, Any]]
    request_headers: list[dict[str, str]]
    metadata: dict[str, Any]


class PydollChallengeError(RuntimeError):
    pass


CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verify you are human",
    "performing security verification",
    "cf-chl-",
)


class PersistentPydollRuntime:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._sessions: dict[tuple[str, str, bool], PydollSession] = {}

    def fetch(self, watch_target: WatchTarget) -> tuple[str, int]:
        return self._submit(self._fetch(watch_target))

    def close(self) -> None:
        if self._loop is None:
            return
        self._submit(self._close_sessions())
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._loop = None
        self._thread = None

    async def _fetch(self, watch_target: WatchTarget) -> tuple[str, int]:
        config = watch_target.parser_config
        profile_dir = pydoll_profile_dir(watch_target)
        binary = str(config.get("pydoll_binary") or "")
        headless = bool(config.get("pydoll_headless", False))
        key = (str(profile_dir.resolve()), binary, headless)
        session = self._sessions.get(key)
        if session is None:
            session = await start_pydoll_session(watch_target)
            self._sessions[key] = session
        return await navigate_pydoll_session(session, watch_target)

    async def _close_sessions(self) -> None:
        for session in self._sessions.values():
            await session.browser.stop()
        self._sessions.clear()

    def _submit(self, coroutine):
        self._ensure_loop()
        future: Future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()


PERSISTENT_PYDOLL_RUNTIME = PersistentPydollRuntime()


def fetch_product_page_pydoll(watch_target: WatchTarget) -> tuple[str, int]:
    if watch_target.parser_config.get("pydoll_keep_open", False):
        return PERSISTENT_PYDOLL_RUNTIME.fetch(watch_target)
    return asyncio.run(_fetch_once(watch_target))


def refresh_cloudflare_api_session(
    watch_target: WatchTarget,
    api_url: str | None = None,
) -> CloudflareBrowserSession:
    return asyncio.run(_refresh_cloudflare_api_session(watch_target, api_url))


async def _fetch_once(watch_target: WatchTarget) -> tuple[str, int]:
    session = await start_pydoll_session(watch_target)
    try:
        return await navigate_pydoll_session(session, watch_target)
    finally:
        await session.browser.stop()


async def start_pydoll_session(watch_target: WatchTarget) -> PydollSession:
    options = pydoll_options(watch_target)
    browser = Chrome(options=options)
    tab = await browser.start()
    return PydollSession(browser=browser, tab=tab)


async def navigate_pydoll_session(
    session: PydollSession,
    watch_target: WatchTarget,
    url: str | None = None,
) -> tuple[str, int]:
    wait_seconds = int(watch_target.parser_config.get("pydoll_wait_seconds", 5))
    challenge_wait_seconds = int(
        watch_target.parser_config.get("pydoll_challenge_wait_seconds", 60)
    )
    await session.tab.go_to(
        url or watch_target.url,
        timeout=watch_target.store.timeout_seconds,
    )
    await asyncio.sleep(wait_seconds)
    html = await session.tab.page_source
    waited = 0
    while _is_challenge_html(html) and waited < challenge_wait_seconds:
        await asyncio.sleep(1)
        waited += 1
        html = await session.tab.page_source
    return html, 200


async def _refresh_cloudflare_api_session(
    watch_target: WatchTarget,
    api_url: str | None,
) -> CloudflareBrowserSession:
    session = await start_pydoll_session(watch_target)
    try:
        browser_url = str(watch_target.parser_config.get("browser_url") or watch_target.url)
        html, _status_code = await navigate_pydoll_session(
            session,
            watch_target,
            url=browser_url,
        )
        if _is_challenge_html(html):
            raise PydollChallengeError(
                "Cloudflare challenge remained after Pydoll navigation."
            )

        browser_state = await collect_browser_state(session)
        cookies = await session.browser.get_cookies()
        request_headers = fallback_headers_from_browser_state(browser_state, browser_url)
        browser_api_status = None
        browser_api_error = ""
        if api_url:
            try:
                browser_api_status, captured_headers = await capture_browser_api_headers(
                    session,
                    api_url,
                )
                if captured_headers:
                    request_headers = captured_headers
            except Exception as exc:
                browser_api_error = f"{type(exc).__name__}: {exc}"

        return CloudflareBrowserSession(
            cookies=cookies,
            request_headers=request_headers,
            metadata={
                "browser_url": browser_url,
                "current_url": browser_state.get("currentUrl"),
                "browser_api_status": browser_api_status,
                "browser_api_error": browser_api_error,
                "cookies_count": len(cookies),
                "headers_count": len(request_headers),
            },
        )
    finally:
        await session.browser.stop()


async def collect_browser_state(session: PydollSession) -> dict[str, Any]:
    result = await session.tab.execute_script(
        """
        return {
            currentUrl: location.href,
            userAgent: navigator.userAgent,
            language: navigator.language,
            languages: Array.from(navigator.languages || [])
        };
        """,
        return_by_value=True,
    )
    value = _script_value(result)
    return value if isinstance(value, dict) else {}


async def capture_browser_api_headers(
    session: PydollSession,
    api_url: str,
) -> tuple[int | None, list[dict[str, str]]]:
    response = await session.tab.request.get(
        api_url,
        credentials="include",
        cache="no-store",
    )
    headers = getattr(response, "request_headers", None) or []
    status_code = getattr(response, "status_code", None)
    return status_code, headers


def fallback_headers_from_browser_state(
    browser_state: dict[str, Any],
    referer: str,
) -> list[dict[str, str]]:
    headers = []
    user_agent = browser_state.get("userAgent")
    language = browser_state.get("language")
    if user_agent:
        headers.append({"name": "user-agent", "value": str(user_agent)})
    if language:
        headers.append({"name": "accept-language", "value": str(language)})
    headers.extend(
        [
            {"name": "accept", "value": "application/json, text/plain, */*"},
            {"name": "cache-control", "value": "no-cache"},
            {"name": "pragma", "value": "no-cache"},
            {"name": "referer", "value": referer},
            {"name": "sec-fetch-dest", "value": "empty"},
            {"name": "sec-fetch-mode", "value": "cors"},
            {"name": "sec-fetch-site", "value": "same-origin"},
        ]
    )
    return headers


def pydoll_options(watch_target: WatchTarget) -> ChromiumOptions:
    config = watch_target.parser_config
    profile_dir = pydoll_profile_dir(watch_target).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    options = ChromiumOptions()
    options.headless = bool(config.get("pydoll_headless", False))
    options.add_argument(f"--user-data-dir={profile_dir}")
    if config.get("pydoll_binary"):
        options.binary_location = str(config["pydoll_binary"])
    return options


def pydoll_profile_dir(watch_target: WatchTarget) -> Path:
    configured = watch_target.parser_config.get("pydoll_profile_dir")
    return Path(configured or f".pydoll/{watch_target.store_id}")


def _is_challenge_html(html: str) -> bool:
    beginning = html[:5000].lower()
    return any(marker in beginning for marker in CHALLENGE_MARKERS)


def _script_value(result: dict[str, Any]) -> Any:
    return result.get("result", {}).get("result", {}).get("value")
