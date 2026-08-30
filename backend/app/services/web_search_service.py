from __future__ import annotations

import base64
import ipaddress
import os
import re
import socket
import ssl
from collections import OrderedDict
from dataclasses import dataclass
from html.parser import HTMLParser
from threading import Lock
from time import monotonic, sleep
from typing import Literal
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx
import httpcore


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    content: str = ""
    source: Literal["bing", "duckduckgo", "so360"] = "bing"


@dataclass(frozen=True)
class WebSearchResponse:
    query: str
    results: tuple[WebSearchResult, ...]
    cached: bool = False
    error: str | None = None
    source: Literal["bing", "duckduckgo", "so360"] = "bing"


class _PageTooLargeError(ValueError):
    pass


class _PinnedNetworkBackend:
    def __init__(self, *, hostname: str, port: int, address: str) -> None:
        self._hostname = hostname.casefold()
        self._port = port
        self._address = address
        self._backend = httpcore.SyncBackend()

    def connect_tcp(self, host, port, **kwargs):
        if host.casefold() != self._hostname or port != self._port:
            raise OSError("pinned transport target changed")
        return self._backend.connect_tcp(self._address, port, **kwargs)

    def connect_unix_socket(self, path, **kwargs):
        raise OSError("unix sockets are not allowed for page fetches")

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, *, hostname: str, port: int, address: str) -> None:
        super().__init__(trust_env=False)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            network_backend=_PinnedNetworkBackend(
                hostname=hostname,
                port=port,
                address=address,
            ),
        )


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


class _DuckDuckGoResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[WebSearchResult] = []
        self._current: dict[str, object] | None = None
        self._title_depth = 0
        self._snippet_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "result__a" in classes:
            self._finish_result()
            self._current = {
                "title": [],
                "url": attributes.get("href") or "",
                "snippet": [],
            }
            self._title_depth = 1
        elif self._current is not None and "result__snippet" in classes:
            self._snippet_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        if self._title_depth:
            self._title_depth = 0
        elif self._snippet_depth:
            self._snippet_depth = 0

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _collapse_whitespace(data)
        if not text:
            return
        if self._title_depth:
            title = self._current["title"]
            assert isinstance(title, list)
            title.append(text)
        elif self._snippet_depth:
            snippet = self._current["snippet"]
            assert isinstance(snippet, list)
            snippet.append(text)

    def close(self) -> None:
        super().close()
        self._finish_result()

    def _finish_result(self) -> None:
        if self._current is None:
            return
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
                    source="duckduckgo",
                )
            )
        self._current = None
        self._title_depth = 0
        self._snippet_depth = 0


class _So360ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[WebSearchResult] = []
        self._current: dict[str, object] | None = None
        self._container_tag = ""
        self._list_depth = 0
        self._heading_depth = 0
        self._link_depth = 0
        self._snippet_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if (
            tag in {"li", "div"}
            and self._current is None
            and "res-list" in classes
        ):
            self._current = {
                "title": [],
                "url": attributes.get("data-pcurl") or "",
                "snippet": [],
            }
            self._container_tag = tag
            self._list_depth = 1
            return
        if self._current is None:
            return
        if tag == self._container_tag:
            self._list_depth += 1
        if self._snippet_depth:
            self._snippet_depth += 1
        elif classes.intersection(
            {"summary", "res-summary", "res-list-summary", "res-desc"}
        ):
            self._snippet_depth = 1
        if tag == "h3":
            self._heading_depth += 1
        elif tag == "a" and self._heading_depth:
            self._link_depth += 1
            if not self._current["url"]:
                self._current["url"] = (
                    attributes.get("data-mdurl")
                    or attributes.get("href")
                    or ""
                )

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if self._snippet_depth:
            self._snippet_depth -= 1
        if tag == "a" and self._link_depth:
            self._link_depth -= 1
        elif tag == "h3" and self._heading_depth:
            self._heading_depth -= 1
        elif tag == self._container_tag:
            self._list_depth -= 1
            if self._list_depth == 0:
                self._finish_result()

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = _collapse_whitespace(data)
        if not text:
            return
        if self._heading_depth:
            title = self._current["title"]
            assert isinstance(title, list)
            title.append(text)
        elif self._snippet_depth:
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
                    source="so360",
                )
            )
        self._current = None
        self._container_tag = ""
        self._list_depth = 0
        self._heading_depth = 0
        self._link_depth = 0
        self._snippet_depth = 0


class _ReadableTextParser(HTMLParser):
    _SKIPPED_TAGS = frozenset(
        {"script", "style", "noscript", "svg", "template", "canvas"}
    )
    _BLOCK_TAGS = frozenset(
        {
            "article",
            "blockquote",
            "br",
            "dd",
            "div",
            "dt",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "main",
            "p",
            "section",
            "table",
            "td",
            "th",
            "tr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in self._SKIPPED_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = _collapse_whitespace(data)
        if text:
            self._parts.append(text)

    def text(self) -> str:
        lines = []
        for value in " ".join(self._parts).splitlines():
            line = _collapse_whitespace(value)
            if line and (not lines or line != lines[-1]):
                lines.append(line)
        return "\n".join(lines)


class WebSearchService:
    SEARCH_URL = "https://www.bing.com/search"
    ALTERNATIVE_SEARCH_URL = "https://html.duckduckgo.com/html/"
    DOMESTIC_SEARCH_URL = "https://m.so.com/s"
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
        search_cache_max_entries: int = 128,
        page_cache_max_entries: int = 256,
        duckduckgo_enabled: bool | None = None,
        so360_enabled: bool | None = None,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = max(0, cache_ttl_seconds)
        self._minimum_interval_seconds = max(0, minimum_interval_seconds)
        self._search_cache_max_entries = max(1, search_cache_max_entries)
        self._page_cache_max_entries = max(1, page_cache_max_entries)
        self._duckduckgo_enabled = (
            _env_flag("WEB_SEARCH_DDG_ENABLED", default=True)
            if duckduckgo_enabled is None
            else duckduckgo_enabled
        )
        self._so360_enabled = (
            _env_flag("WEB_SEARCH_360_ENABLED", default=True)
            if so360_enabled is None
            else so360_enabled
        )
        self._cache: OrderedDict[
            str, tuple[float, tuple[WebSearchResult, ...]]
        ] = OrderedDict()
        self._page_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
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
        # Cache the complete upstream result window. A caller that initially asks
        # for one item must not permanently truncate later requests for the same
        # query while the cache entry is still fresh.
        results = tuple(_deduplicate(parser.results)[:5])
        if not results:
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error="必应没有返回可解析的搜索结果",
            )
        with self._lock:
            self._cache[cache_key] = (monotonic(), results)
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self._search_cache_max_entries:
                self._cache.popitem(last=False)
        return WebSearchResponse(query=safe_query, results=results[:limit])

    def search_alternative(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> WebSearchResponse:
        safe_query = _sanitize_query(query)
        if not safe_query:
            return WebSearchResponse(
                query="",
                results=(),
                error="搜索词为空或只包含了被移除的敏感信息",
                source="duckduckgo",
            )
        limit = min(max(1, max_results), 5)
        domestic_error: str | None = None
        if self._so360_enabled:
            domestic = self.search_domestic(safe_query, max_results=limit)
            if domestic.results:
                return domestic
            domestic_error = domestic.error
        if not self._duckduckgo_enabled:
            bing_fallback = self.search(safe_query, max_results=limit)
            if bing_fallback.results:
                return bing_fallback
            errors = [item for item in (domestic_error, bing_fallback.error) if item]
            return WebSearchResponse(
                query=safe_query,
                results=(),
                error="；".join(errors) or "备用搜索没有返回可用结果",
                source="bing",
            )
        cache_key = f"duckduckgo:{safe_query.casefold()}"
        cached = self._get_cached(cache_key, limit)
        if cached is not None:
            return WebSearchResponse(
                query=safe_query,
                results=cached,
                cached=True,
                source="duckduckgo",
            )

        self._wait_for_rate_limit()
        try:
            response = self._alternative_request(safe_query)
            response.raise_for_status()
        except httpx.TimeoutException:
            error = "DuckDuckGo 搜索超时"
        except httpx.HTTPStatusError as exc:
            error = f"DuckDuckGo 搜索返回 HTTP {exc.response.status_code}"
        except httpx.HTTPError as exc:
            error = f"DuckDuckGo 搜索连接失败：{type(exc).__name__}"
        else:
            lowered = response.text.casefold()
            if "anomaly-modal" in lowered or "challenge-form" in lowered:
                error = "DuckDuckGo 要求完成人机验证"
            else:
                parser = _DuckDuckGoResultsParser()
                parser.feed(response.text)
                parser.close()
                results = tuple(_deduplicate(parser.results)[:5])
                if results:
                    with self._lock:
                        self._cache[cache_key] = (monotonic(), results)
                        self._cache.move_to_end(cache_key)
                        while len(self._cache) > self._search_cache_max_entries:
                            self._cache.popitem(last=False)
                    return WebSearchResponse(
                        query=safe_query,
                        results=results[:limit],
                        source="duckduckgo",
                    )
                error = "DuckDuckGo 没有返回可解析的搜索结果"
        bing_fallback = self.search(safe_query, max_results=limit)
        if bing_fallback.results:
            return bing_fallback
        fallback_error = bing_fallback.error or "必应没有返回可用结果"
        return WebSearchResponse(
            query=safe_query,
            results=(),
            error=f"{error}；必应回退失败：{fallback_error}",
            source="bing",
        )

    def search_domestic(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> WebSearchResponse:
        safe_query = _sanitize_query(query)
        if not safe_query:
            return WebSearchResponse(
                query="",
                results=(),
                error="搜索词为空或只包含了被移除的敏感信息",
                source="so360",
            )
        limit = min(max(1, max_results), 5)
        cache_key = f"so360:{safe_query.casefold()}"
        cached = self._get_cached(cache_key, limit)
        if cached is not None:
            return WebSearchResponse(
                query=safe_query,
                results=cached,
                cached=True,
                source="so360",
            )

        self._wait_for_rate_limit()
        try:
            response = self._domestic_request(safe_query)
            response.raise_for_status()
        except httpx.TimeoutException:
            error = "360 搜索超时"
        except httpx.HTTPStatusError as exc:
            error = f"360 搜索返回 HTTP {exc.response.status_code}"
        except httpx.HTTPError as exc:
            error = f"360 搜索连接失败：{type(exc).__name__}"
        else:
            lowered = response.text.casefold()
            if "安全验证" in response.text or "captcha" in lowered:
                error = "360 搜索要求完成人机验证"
            else:
                parser = _So360ResultsParser()
                parser.feed(response.text)
                parser.close()
                results = tuple(_deduplicate(parser.results)[:5])
                if results:
                    with self._lock:
                        self._cache[cache_key] = (monotonic(), results)
                        self._cache.move_to_end(cache_key)
                        while len(self._cache) > self._search_cache_max_entries:
                            self._cache.popitem(last=False)
                    return WebSearchResponse(
                        query=safe_query,
                        results=results[:limit],
                        source="so360",
                    )
                error = "360 搜索没有返回可解析的搜索结果"
        return WebSearchResponse(
            query=safe_query,
            results=(),
            error=error,
            source="so360",
        )

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

    def _alternative_request(self, query: str) -> httpx.Response:
        parameters = {"q": query}
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        if self._client is not None:
            return self._client.get(
                self.ALTERNATIVE_SEARCH_URL,
                params=parameters,
                headers=headers,
                timeout=10,
            )
        with httpx.Client(follow_redirects=True) as client:
            return client.get(
                self.ALTERNATIVE_SEARCH_URL,
                params=parameters,
                headers=headers,
                timeout=10,
            )

    def _domestic_request(self, query: str) -> httpx.Response:
        parameters = {"q": query}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        if self._client is not None:
            return self._client.get(
                self.DOMESTIC_SEARCH_URL,
                params=parameters,
                headers=headers,
                timeout=10,
            )
        with httpx.Client(follow_redirects=True) as client:
            return client.get(
                self.DOMESTIC_SEARCH_URL,
                params=parameters,
                headers=headers,
                timeout=10,
            )

    def fetch_pages(
        self,
        results: tuple[WebSearchResult, ...],
        *,
        max_pages: int = 2,
    ) -> tuple[WebSearchResult, ...]:
        limit = min(max(0, max_pages), 3)
        enriched: list[WebSearchResult] = []
        for index, result in enumerate(results):
            content = self._fetch_page(result.url) if index < limit else ""
            enriched.append(
                WebSearchResult(
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                    content=content,
                    source=result.source,
                )
            )
        return tuple(enriched)

    def _fetch_page(self, url: str) -> str:
        cached = self._get_cached_page(url)
        if cached is not None:
            return cached
        current_url = url
        try:
            for _ in range(4):
                if not self._is_safe_page_url(current_url):
                    return ""
                response = self._page_request(current_url)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "").strip()
                    if not location:
                        return ""
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not any(
                    allowed in content_type
                    for allowed in (
                        "text/html",
                        "application/xhtml+xml",
                        "text/plain",
                        "application/json",
                    )
                ):
                    return ""
                raw = response.content
                text = _decode_page(raw, content_type)
                if "html" in content_type or "<html" in text[:500].casefold():
                    parser = _ReadableTextParser()
                    parser.feed(text)
                    parser.close()
                    text = parser.text()
                else:
                    text = _collapse_whitespace(text)
                content = text[:8_000]
                if content:
                    with self._lock:
                        self._page_cache[url] = (monotonic(), content)
                        self._page_cache.move_to_end(url)
                        while len(self._page_cache) > self._page_cache_max_entries:
                            self._page_cache.popitem(last=False)
                return content
            return ""
        except (httpx.HTTPError, UnicodeError, ValueError, OSError):
            return ""

    def _page_request(self, url: str) -> httpx.Response:
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain,application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        if self._client is not None:
            with self._client.stream(
                "GET",
                url,
                headers=headers,
                timeout=5,
                follow_redirects=False,
            ) as response:
                return self._bounded_response(response)

        hostname, port, addresses = self._resolve_page_addresses(url)
        last_error: Exception | None = None
        for address in addresses:
            try:
                transport = _PinnedHTTPTransport(
                    hostname=hostname,
                    port=port,
                    address=address,
                )
                with httpx.Client(
                    transport=transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    with client.stream("GET", url, headers=headers, timeout=5) as response:
                        return self._bounded_response(response)
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise OSError("page hostname did not resolve to a public address")

    @staticmethod
    def _bounded_response(response: httpx.Response) -> httpx.Response:
        maximum = 512 * 1024
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                declared_bytes = int(declared)
            except ValueError as exc:
                raise _PageTooLargeError("invalid page content-length") from exc
            if declared_bytes < 0:
                raise _PageTooLargeError("invalid page content-length")
            if declared_bytes > maximum:
                raise _PageTooLargeError("page response exceeds byte limit")
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > maximum:
                raise _PageTooLargeError("page response exceeds byte limit")
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=bytes(content),
            request=response.request,
            extensions=response.extensions,
        )

    def _is_safe_page_url(self, url: str) -> bool:
        try:
            self._resolve_page_addresses(url)
            return True
        except (OSError, ValueError):
            return False

    def _resolve_page_addresses(self, url: str) -> tuple[str, int, tuple[str, ...]]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("unsupported page URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("page URL credentials are not allowed")
        expected_port = 443 if parsed.scheme == "https" else 80
        port = parsed.port or expected_port
        if port != expected_port:
            raise ValueError("non-standard page ports are not allowed")
        hostname = parsed.hostname
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            if self._client is not None:
                return hostname, port, (hostname,)
            resolved = tuple(
                dict.fromkeys(
                    item[4][0]
                    for item in socket.getaddrinfo(
                        hostname,
                        port,
                        type=socket.SOCK_STREAM,
                    )
                )
            )
            if not resolved:
                raise OSError("page hostname did not resolve")
            addresses = tuple(ipaddress.ip_address(item) for item in resolved)
        else:
            addresses = (literal,)
        if not all(_is_public_address(item) for item in addresses):
            raise ValueError("page hostname resolves to a non-public address")
        return hostname, port, tuple(str(item) for item in addresses)

    def _get_cached_page(self, url: str) -> str | None:
        with self._lock:
            entry = self._page_cache.get(url)
            if entry is None:
                return None
            cached_at, content = entry
            if monotonic() - cached_at > self._cache_ttl_seconds:
                self._page_cache.pop(url, None)
                return None
            self._page_cache.move_to_end(url)
            return content

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
            self._cache.move_to_end(cache_key)
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


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decode_page(raw: bytes, content_type: str) -> str:
    charset_match = re.search(r"charset=([\w-]+)", content_type)
    candidates = [charset_match.group(1)] if charset_match else []
    head = raw[:2_048].decode("ascii", errors="ignore")
    meta_match = re.search(r"charset=[\"']?([\w-]+)", head, re.IGNORECASE)
    if meta_match:
        candidates.append(meta_match.group(1))
    candidates.extend(["utf-8", "gb18030"])
    for encoding in dict.fromkeys(candidates):
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _sanitize_query(value: str) -> str:
    query = _collapse_whitespace(value)
    query = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", query)
    query = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", " ", query)
    query = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", " ", query)
    return _collapse_whitespace(query)[:160]


def _normalize_result_url(value: str) -> str:
    if value.startswith("//"):
        value = f"https:{value}"
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

    if (
        parsed.hostname.casefold().endswith("duckduckgo.com")
        and parsed.path == "/l/"
    ):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            parsed = urlparse(target)
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
