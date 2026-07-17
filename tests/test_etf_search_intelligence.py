# -*- coding: utf-8 -*-

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.search_service import SearchResponse, SearchResult, SearchService
from src.services.etf_search_intelligence import resolve_etf_profile


def _item(title: str, *, days_ago: int = 0, url_suffix: str = "1", snippet: str = "") -> SearchResult:
    return SearchResult(
        title=title,
        snippet=snippet,
        url=f"https://example.com/{url_suffix}",
        source="example.com",
        published_date=(datetime.now().date() - timedelta(days=days_ago)).isoformat(),
    )


def _response(query: str, items: list[SearchResult], *, success: bool = True) -> SearchResponse:
    return SearchResponse(
        query=query,
        results=items,
        provider="Anspire",
        success=success,
        error_message=None if success else "provider failed",
    )


def _service() -> SearchService:
    return SearchService(
        anspire_keys=["test-key"],
        searxng_public_instances_enabled=False,
    )


def test_etf_profile_covers_current_and_generic_types() -> None:
    sector_codes = {
        "159516": "半导体设备ETF国泰",
        "159667": "工业母机ETF国泰",
        "159766": "旅游ETF富国",
        "159796": "电池ETF汇添富",
        "159819": "人工智能ETF易方达",
        "159869": "游戏ETF华夏",
        "512200": "房地产ETF南方",
        "512690": "酒ETF鹏华",
        "512710": "军工龙头ETF富国",
        "512800": "银行ETF华宝",
        "512880": "证券ETF国泰",
        "515220": "煤炭ETF国泰",
        "515790": "光伏ETF华泰柏瑞",
        "515880": "通信ETF国泰",
    }
    for code, name in sector_codes.items():
        assert resolve_etf_profile(code, name).kind == "cn_sector_theme"

    for code, name in {
        "159570": "港股通创新药ETF汇添富",
        "159941": "纳指ETF广发",
        "513050": "中概互联网ETF易方达",
    }.items():
        assert resolve_etf_profile(code, name).kind == "cross_border"

    assert resolve_etf_profile("518880", "黄金ETF华安").kind == "commodity"
    assert resolve_etf_profile("510300", "沪深300ETF").kind == "broad_index"
    assert resolve_etf_profile("515180", "红利低波ETF").kind == "strategy"
    assert resolve_etf_profile("511010", "国债ETF").kind == "bond"
    generic = resolve_etf_profile("159999", "ETF")
    assert generic.kind == "generic_etf"
    assert not generic.underlying_driver_enabled

    for name in ("未知ETF", "科技ETF", "未来ETF", "某某ETF"):
        unknown = resolve_etf_profile("588888", name)
        assert unknown.kind == "generic_etf"
        assert unknown.underlying_terms == ()
        assert not unknown.underlying_driver_enabled


def test_etf_comprehensive_uses_two_anspire_requests_and_deterministic_routing() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(
        side_effect=[
            _response(
                "fresh",
                [
                    _item("518880 黄金ETF华安发布高溢价风险提示", url_suffix="risk"),
                    _item("黄金价格受美元和实际利率回落推动", url_suffix="driver"),
                    _item("518880 黄金ETF基金份额净流入扩大", url_suffix="flow"),
                    _item("黄金ETF今日上涨2% 成交额创新高", url_suffix="recap"),
                ],
            ),
            _response(
                "analysis",
                [
                    _item("黄金供需与央行购金支撑中期趋势", url_suffix="outlook"),
                    _item("黄金估值与实际利率关系进入机构研报", url_suffix="valuation"),
                ],
            ),
        ]
    )

    results = service.search_comprehensive_intel("518880", "黄金ETF华安", max_searches=5)

    assert provider.search.call_count == 2
    first_kwargs = provider.search.call_args_list[0].kwargs
    second_kwargs = provider.search.call_args_list[1].kwargs
    assert first_kwargs == {"max_results": 18, "days": 3, "timeout": 10.0, "retry_enabled": False}
    assert second_kwargs == {"max_results": 18, "days": 30, "timeout": 10.0, "retry_enabled": False}
    assert results["risk_check"].results[0].title.endswith("高溢价风险提示")
    assert any(
        item.relevance_category == "etf_underlying_driver"
        for response in results.values()
        for item in response.results
    )
    assert all("成交额创新高" not in item.title for response in results.values() for item in response.results)
    report = service.format_intel_report(results, "黄金ETF华安")
    assert "产品风险与交易限制" in report
    assert "底层驱动，不代表ETF产品事实" in report


def test_etf_group_failure_does_not_fallback_or_pollute_other_group() -> None:
    service = SearchService(
        anspire_keys=["test-key"],
        bocha_keys=["bocha-key"],
        searxng_base_urls=["https://searx.example.org"],
        searxng_public_instances_enabled=False,
    )
    anspire = service._anspire_provider
    assert anspire is not None
    bocha = next(provider for provider in service._providers if provider.name == "Bocha")
    searxng = next(provider for provider in service._providers if provider.name == "SearXNG")
    anspire.search = MagicMock(
        side_effect=[
            _response("fresh", [], success=False),
            _response("analysis", [_item("证券行业景气与政策催化趋势", url_suffix="ok")]),
        ]
    )
    bocha.search = MagicMock()
    searxng.search = MagicMock()

    results = service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)

    assert anspire.search.call_count == 2
    bocha.search.assert_not_called()
    searxng.search.assert_not_called()
    assert list(results) == ["industry"]


def test_etf_cache_refreshes_fresh_group_only_after_fifteen_minutes() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    fresh = _response("fresh", [_item("证券行业政策催化景气上行", url_suffix="fresh")])
    analysis = _response("analysis", [_item("证券行业估值与景气机构观点", url_suffix="analysis")])
    provider.search = MagicMock(side_effect=[fresh, analysis, fresh])

    with patch("src.search_service.time.time", return_value=1000):
        first = service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)
        second = service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)
    assert first and second
    assert provider.search.call_count == 2

    with patch("src.search_service.time.time", return_value=1901):
        third = service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)
    assert third
    assert provider.search.call_count == 3
    assert provider.search.call_args.kwargs["days"] == 3


def test_etf_cache_is_shared_across_search_service_instances() -> None:
    first = _service()
    second = _service()
    first_provider = first._anspire_provider
    second_provider = second._anspire_provider
    assert first_provider is not None and second_provider is not None
    first_provider.search = MagicMock(
        side_effect=[
            _response("fresh", [_item("证券行业政策催化景气上行", url_suffix="shared-fresh")]),
            _response("analysis", [_item("证券行业估值与景气机构观点", url_suffix="shared-analysis")]),
        ]
    )
    second_provider.search = MagicMock()

    first_results = first.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)
    second_results = second.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)

    assert first_results and second_results
    assert first_provider.search.call_count == 2
    second_provider.search.assert_not_called()


def test_etf_concurrent_cross_instance_cold_start_uses_one_owner_per_group() -> None:
    first = _service()
    second = _service()
    call_count = 0
    call_lock = threading.Lock()

    def search(_query, *, days, **_kwargs):
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.05)
        if days == 3:
            return _response("fresh", [_item("证券行业政策催化景气上行", url_suffix="owner-fresh")])
        return _response("analysis", [_item("证券行业估值与景气机构观点", url_suffix="owner-analysis")])

    assert first._anspire_provider is not None and second._anspire_provider is not None
    first._anspire_provider.search = MagicMock(side_effect=search)
    second._anspire_provider.search = MagicMock(side_effect=search)
    barrier = threading.Barrier(2)
    results: list[dict[str, SearchResponse]] = []

    def worker(service: SearchService) -> None:
        barrier.wait(timeout=1)
        results.append(service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6))

    threads = [threading.Thread(target=worker, args=(service,)) for service in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert len(results) == 2
    assert all(result for result in results)
    assert call_count == 2


def test_etf_unknown_or_expired_dates_and_ambiguous_underlying_are_rejected() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(
        side_effect=[
            _response(
                "fresh",
                [
                    SearchResult("证券行业政策催化", "", "https://example.com/u", "example.com", None),
                    _item("证券行业政策催化", days_ago=3, url_suffix="old-fresh"),
                ],
            ),
            _response(
                "analysis",
                [_item("证券行业估值景气", days_ago=30, url_suffix="old-analysis")],
            ),
        ]
    )
    results = service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=6)
    assert results == {}
    assert service.format_intel_report(results, "证券ETF国泰") == ""

    generic = _service()
    generic_provider = generic._anspire_provider
    assert generic_provider is not None
    generic_provider.search = MagicMock(
        side_effect=[
            _response("fresh", [_item("人工智能政策催化", url_suffix="ambiguous")]),
            _response("analysis", [_item("人工智能估值景气", url_suffix="ambiguous-analysis")]),
        ]
    )
    assert generic.search_comprehensive_intel("159999", "ETF", max_searches=6) == {}


def test_etf_plain_market_recap_and_url_only_product_identity_are_rejected() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(
        side_effect=[
            _response(
                "fresh",
                [
                    _item("黄金价格今日上涨2%", url_suffix="plain-price-recap"),
                    _item(
                        "某基金发布暂停申购公告",
                        url_suffix="518880-url-only",
                    ),
                ],
            ),
            _response("analysis", []),
        ]
    )

    assert service.search_comprehensive_intel("518880", "黄金ETF华安", max_searches=6) == {}


def test_etf_without_anspire_excludes_searxng_from_legacy_comprehensive_path() -> None:
    service = SearchService(
        searxng_base_urls=["https://searx.example.org"],
        searxng_public_instances_enabled=False,
    )
    searxng = next(provider for provider in service._providers if provider.name == "SearXNG")
    searxng.search = MagicMock()

    assert service.search_comprehensive_intel("512880", "证券ETF国泰", max_searches=5) == {}
    searxng.search.assert_not_called()
