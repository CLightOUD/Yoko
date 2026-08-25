from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from threading import Lock
from time import monotonic, sleep
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class WebSearchResponse:
    query: str
    results: tuple[WebSearchResult, ...]
    cached: bool = False
    error: str | None = None


class _BingResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[WebSearchResult] = []
        self._current: dict[str, object] | None = None
        self._list_depth = 0
        self._heading_depth = 0
        self._link_depth = 0
        self._paragraph_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "li" and self._current is None and "b_algo" in classes:
            self._current = {"title": [], "url": "", "snippet": []}
            self._list_depth = 1
            return
        if self._current is None:
            return
        if tag == "li":
            self._list_depth += 1
        elif tag == "h2":
            self._heading_depth += 1
        elif tag == "a" and self._heading_depth:
            self._link_depth += 1
            if not self._current["url"]:
                self._current["url"] = attributes.get("href") or ""
        elif tag == "p":
            self._paragraph_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._link_depth:
            self._link_depth -= 1
        elif tag == "h2" and self._heading_depth:
            self._heading_depth -= 1
        elif tag == "p" and self._paragraph_depth:
            self._paragraph_depth -= 1
        elif tag == "li":
            self._list_depth -= 1
            if self._list_depth == 0:
                self._finish_result()

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _collapse_whitespace(data)
        if not text:
            return
        if self._link_depth:
            title = self._current["title"]
            assert isinstance(title, list)
            title.append(text)
        elif self._paragraph_depth:
            snippet = self._current["snippet"]
            assert isinstance(snippet, list)
            snippet.append(text)

    def close(self) -> None:
        super().close()
        if self._current is not None:
            self._finish_result()

    def _finish_result(self) -> None:
        assert self._current is not None
        title_parts = self._current["title"]
        snippet_parts = self._current["snippet"]
        assert isinstance(title_parts, list)
        assert isinstance(snippet_parts, list)
        title = _collapse_whitespace(" ".join(title_parts))
        snippet = _collapse_whitespace(" ".join(snippet_parts))
        url = _normalize_result_url(str(self._current["url"]))
        if title and url:
            self.results.append(
                WebSearchResult(
                    title=title[:200],
                    url=url[:2048],
                    snippet=snippet[:500],
                )
            )
        self._current = None
        self._list_depth = 0
        self._heading_depth = 0
        self._link_depth = 0
        self._paragraph_depth = 0


class WebSearchService:
    SEARCH_URL = "https://www.bing.com/search"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        cache_ttl_seconds: float = 900,
        minimum_interval_seconds: float = 1,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = max(0, cache_ttl_seconds)
        self._minimum_interval_seconds = max(0, minimum_interval_seconds)
        self._cache: dict[str, tuple[float, tuple[WebSearchResult, ...]]] = {}
        self._lock = Lock()
        self._last_request_started = 0.0

    def search(self, query: str, *, max_results: int = 5) -> WebSearchResponse:
        safe_query = _sanitize_query(query)
        if not safe_query:
            return WebSearchResponse(
                query="",
                results=(),
                error="搜索词为空或只包含了被移除的敏感信息",
            )
        limit = min(max(1, max_results), 5)
        cache_key = safe_query.casefold()
        cached = self._get_cached(cache_key, limit)
        if cached is not None:
            return WebSearchResponse(
                query=safe_query,
                results=cached,
                cached=True,
            )

        self._wait_for_rate_limit()
        try:
            response = self._request(safe_query)
            response.raise_for_status()
        except httpx.TimeoutException:
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error="必应搜索超时",
            )
        except httpx.HTTPStatusError as exc:
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error=f"必应搜索返回 HTTP {exc.response.status_code}",
            )
        except httpx.HTTPError as exc:
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error=f"必应搜索连接失败：{type(exc).__name__}",
            )

        html = response.text
        lowered = html.casefold()
        if "b_captcha" in lowered or "unusual traffic" in lowered:
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error="必应要求完成人机验证",
            )

        parser = _BingResultsParser()
        parser.feed(html)
        parser.close()
        results = tuple(_deduplicate(parser.results)[:limit])
        if not results:
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error="必应没有返回可解析的搜索结果",
            )
        with self._lock:
            self._cache[cache_key] = (monotonic(), results)
        return WebSearchResponse(query=safe_query, results=results)

    def _request(self, query: str) -> httpx.Response:
        parameters = {
            "q": query,
            "setlang": "zh-Hans",
            "cc": "cn",
            "count": "5",
        }
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        if self._client is not None:
            return self._client.get(
                self.SEARCH_URL,
                params=parameters,
                headers=headers,
                timeout=5,
            )
        with httpx.Client(follow_redirects=True) as client:
            return client.get(
                self.SEARCH_URL,
                params=parameters,
                headers=headers,
                timeout=5,
            )

    def _get_cached(
        self,
        cache_key: str,
        limit: int,
    ) -> tuple[WebSearchResult, ...] | None:
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            cached_at, results = entry
            if monotonic() - cached_at > self._cache_ttl_seconds:
                self._cache.pop(cache_key, None)
                return None
            return results[:limit]

    def _wait_for_rate_limit(self) -> None:
        with self._lock:
            current = monotonic()
            delay = self._minimum_interval_seconds - (
                current - self._last_request_started
            )
            if delay > 0:
                sleep(delay)
            self._last_request_started = monotonic()


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sanitize_query(value: str) -> str:
    query = _collapse_whitespace(value)
    query = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", query)
    query = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", " ", query)
    query = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", " ", query)
    return _collapse_whitespace(query)[:160]


def _normalize_result_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""

    if parsed.hostname.casefold().endswith("bing.com") and parsed.path.startswith(
        "/ck/"
    ):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        decoded = _decode_bing_target(encoded)
        if decoded:
            parsed = urlparse(decoded)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return ""

    query_pairs = [
        (key, item)
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        if not key.casefold().startswith("utm_") and key.casefold() != "msclkid"
        for item in values
    ]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_pairs, doseq=True),
            "",
        )
    )


def _decode_bing_target(value: str) -> str:
    encoded = value[2:] if value.startswith("a1") else value
    if not encoded:
        return ""
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _deduplicate(results: list[WebSearchResult]) -> list[WebSearchResult]:
    seen: set[str] = set()
    unique: list[WebSearchResult] = []
    for result in results:
        key = result.url.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique
