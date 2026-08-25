from __future__ import annotations

import base64
from urllib.parse import quote

import httpx

from backend.app.services.web_search_service import WebSearchService


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_bing_search_parses_deduplicates_and_caches_results() -> None:
    calls = 0
    target = "https://example.com/article?utm_source=bing&id=7#part"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    redirect = f"https://www.bing.com/ck/a?u=a1{quote(encoded)}"
    html = f"""
    <html><body><ol>
      <li class="b_algo">
        <h2><a href="{redirect}">养老 <strong>政策</strong> 更新</a></h2>
        <div class="b_caption"><p>这是 第一条 摘要。</p></div>
      </li>
      <li class="b_algo">
        <h2><a href="https://example.com/article?id=7">重复结果</a></h2>
        <div class="b_caption"><p>不应重复返回。</p></div>
      </li>
      <li class="b_algo">
        <h2><a href="https://gov.example.cn/notice">官方通知</a></h2>
        <div class="b_caption"><p>第二条摘要。</p></div>
      </li>
    </ol></body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["q"] == "养老政策 最新"
        return httpx.Response(200, text=html, request=request)

    service = WebSearchService(
        client=_client(handler),
        cache_ttl_seconds=60,
        minimum_interval_seconds=0,
    )
    first = service.search("  养老政策   最新  ")
    second = service.search("养老政策 最新", max_results=1)

    assert calls == 1
    assert first.error is None
    assert [item.title for item in first.results] == [
        "养老 政策 更新",
        "官方通知",
    ]
    assert first.results[0].url == "https://example.com/article?id=7"
    assert first.results[0].snippet == "这是 第一条 摘要。"
    assert second.cached is True
    assert len(second.results) == 1


def test_search_query_removes_common_direct_identifiers() -> None:
    observed_query = ""
    html = """
    <li class="b_algo"><h2><a href="https://example.com/a">结果</a></h2>
    <p>摘要</p></li>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_query
        observed_query = request.url.params["q"]
        return httpx.Response(200, text=html, request=request)

    service = WebSearchService(
        client=_client(handler),
        minimum_interval_seconds=0,
    )
    result = service.search(
        "查询张阿姨 13800138000 user@example.com 11010519491231002X 的养老政策"
    )

    assert result.results
    assert "13800138000" not in observed_query
    assert "user@example.com" not in observed_query
    assert "11010519491231002X" not in observed_query
    assert "养老政策" in observed_query


def test_search_reports_captcha_and_http_failures_without_raising() -> None:
    captcha_service = WebSearchService(
        client=_client(
            lambda request: httpx.Response(
                200,
                text='<div id="b_captcha">verify</div>',
                request=request,
            )
        ),
        minimum_interval_seconds=0,
    )
    limited_service = WebSearchService(
        client=_client(
            lambda request: httpx.Response(429, text="slow down", request=request)
        ),
        minimum_interval_seconds=0,
    )

    captcha = captcha_service.search("测试")
    limited = limited_service.search("测试")

    assert captcha.results == ()
    assert "人机验证" in (captcha.error or "")
    assert limited.results == ()
    assert "HTTP 429" in (limited.error or "")


def test_search_rejects_query_containing_only_sensitive_identifiers() -> None:
    service = WebSearchService(minimum_interval_seconds=0)

    result = service.search("13800138000 user@example.com")

    assert result.results == ()
    assert "搜索词为空" in (result.error or "")
