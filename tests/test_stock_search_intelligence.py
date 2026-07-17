# -*- coding: utf-8 -*-

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.search_service import SearchResponse, SearchResult, SearchService
from src.services.stock_search_intelligence import ANALYSIS_GROUP, StockSearchDimension


def _item(
    title: str,
    *,
    days_ago: int | None = 0,
    url_suffix: str,
    snippet: str = "",
) -> SearchResult:
    published_date = None
    if days_ago is not None:
        published_date = (datetime.now().date() - timedelta(days=days_ago)).isoformat()
    return SearchResult(
        title=title,
        snippet=snippet,
        url=f"https://example.com/{url_suffix}",
        source="example.com",
        published_date=published_date,
    )


def _response(query: str, items: list[SearchResult], *, success: bool = True) -> SearchResponse:
    return SearchResponse(
        query=query,
        results=items,
        provider="Anspire",
        success=success,
        error_message=None if success else "provider failed",
    )


def _service(**kwargs) -> SearchService:
    return SearchService(
        anspire_keys=["test-key"],
        searxng_public_instances_enabled=False,
        **kwargs,
    )


def _fresh_response() -> SearchResponse:
    return _response(
        "fresh",
        [
            _item("贵州茅台 600519 发布重大经营事件", url_suffix="latest"),
            _item("贵州茅台 600519 发布公司公告", url_suffix="announcement"),
            _item("贵州茅台 600519 因违规被处罚并提示风险", url_suffix="risk"),
        ],
    )


def _analysis_response() -> SearchResponse:
    return _response(
        "analysis",
        [
            _item("贵州茅台 600519 获机构上调评级与目标价", url_suffix="analysis"),
            _item("贵州茅台 600519 发布财报，净利润增长", url_suffix="earnings"),
        ],
    )


def test_stock_pipeline_uses_two_anspire_groups_and_restores_five_dimensions() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(side_effect=[_fresh_response(), _analysis_response()])

    results = service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5)

    assert provider.search.call_count == 2
    assert [call.kwargs["days"] for call in provider.search.call_args_list] == [3, 180]
    assert all(call.kwargs["max_results"] == 18 for call in provider.search.call_args_list)
    assert all(call.kwargs["timeout"] == 10.0 for call in provider.search.call_args_list)
    assert all(call.kwargs["retry_enabled"] is False for call in provider.search.call_args_list)
    assert set(results) == {
        "latest_news",
        "market_analysis",
        "risk_check",
        "announcements",
        "earnings",
    }
    urls = [item.url for response in results.values() for item in response.results]
    assert len(urls) == len(set(urls))


def test_stock_max_searches_one_only_requests_fresh_group() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(return_value=_fresh_response())

    results = service.search_comprehensive_intel("600519", "贵州茅台", max_searches=1)

    provider.search.assert_called_once()
    assert provider.search.call_args.kwargs["days"] == 3
    assert set(results) == {"latest_news"}


def test_stock_internal_analysis_only_dimensions_request_analysis_group() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(return_value=_analysis_response())
    analysis_only = (
        StockSearchDimension(
            name="market_analysis",
            query="贵州茅台 600519 机构研报",
            desc="机构分析",
            group_name=ANALYSIS_GROUP,
            strict_freshness=False,
            tavily_topic=None,
        ),
    )

    with patch("src.search_service.enabled_stock_dimensions", return_value=analysis_only):
        results = service.search_comprehensive_intel("600519", "贵州茅台", max_searches=1)

    provider.search.assert_called_once()
    assert provider.search.call_args.kwargs["days"] == 180
    assert set(results) == {"market_analysis"}


def test_foreign_stock_pipeline_keeps_existing_industry_dimension() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(
        side_effect=[
            _response(
                "fresh",
                [
                    _item("BABA latest company news event", url_suffix="baba-latest"),
                    _item("BABA faces litigation risk", url_suffix="baba-risk"),
                ],
            ),
            _response(
                "analysis",
                [
                    _item("BABA analyst raises target price", url_suffix="baba-analysis"),
                    _item("BABA earnings revenue growth", url_suffix="baba-earnings"),
                    _item("BABA industry competitors and market share outlook", url_suffix="baba-industry"),
                ],
            ),
        ]
    )

    results = service.search_comprehensive_intel("BABA", "Alibaba", max_searches=5)

    assert provider.search.call_count == 2
    assert set(results) == {
        "latest_news",
        "market_analysis",
        "risk_check",
        "earnings",
        "industry",
    }
    assert "announcements" not in results


def test_stock_analysis_group_keeps_unknown_date_and_rejects_out_of_window() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(
        side_effect=[
            _fresh_response(),
            _response(
                "analysis",
                [
                    _item(
                        "贵州茅台 600519 获机构评级与目标价",
                        days_ago=None,
                        url_suffix="unknown",
                    ),
                    _item(
                        "贵州茅台 600519 发布财报，净利润增长",
                        days_ago=179,
                        url_suffix="in-window",
                    ),
                    _item(
                        "贵州茅台 600519 发布旧财报",
                        days_ago=180,
                        url_suffix="out-window",
                    ),
                ],
            ),
        ]
    )

    results = service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5)

    titles = [item.title for response in results.values() for item in response.results]
    assert "贵州茅台 600519 获机构评级与目标价" in titles
    assert "贵州茅台 600519 发布财报，净利润增长" in titles
    assert "贵州茅台 600519 发布旧财报" not in titles


def test_stock_group_rejects_wrong_identity_macro_and_unknown_fresh_date() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(
        side_effect=[
            _response(
                "fresh",
                [
                    _item("五粮液发布重大经营事件", url_suffix="wrong-company"),
                    _item("A股市场今日震荡，白酒板块走强", url_suffix="macro"),
                    _item(
                        "贵州茅台 600519 发布重大经营事件",
                        days_ago=None,
                        url_suffix="unknown-fresh",
                    ),
                ],
            ),
            _response("analysis", [_item("五粮液获机构上调评级", url_suffix="wrong-analysis")]),
        ]
    )

    assert service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5) == {}
    assert provider.search.call_count == 2


def test_stock_same_url_is_not_repeated_across_groups() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    duplicate_url = "https://example.com/shared"
    provider.search = MagicMock(
        side_effect=[
            _response(
                "fresh",
                [
                    SearchResult(
                        title="贵州茅台 600519 发布公司公告",
                        snippet="贵州茅台披露公告",
                        url=duplicate_url,
                        source="example.com",
                        published_date=datetime.now().date().isoformat(),
                    )
                ],
            ),
            _response(
                "analysis",
                [
                    SearchResult(
                        title="贵州茅台 600519 公告获机构评级",
                        snippet="机构上调目标价",
                        url=duplicate_url,
                        source="example.com",
                        published_date=datetime.now().date().isoformat(),
                    )
                ],
            ),
        ]
    )

    results = service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5)

    urls = [item.url for response in results.values() for item in response.results]
    assert urls == [duplicate_url]


def test_stock_successful_empty_groups_do_not_fan_out_to_legacy_provider() -> None:
    service = _service(bocha_keys=["bocha-key"])
    anspire = service._anspire_provider
    assert anspire is not None
    bocha = next(provider for provider in service._providers if provider.name == "Bocha")
    anspire.search = MagicMock(side_effect=[_response("fresh", []), _response("analysis", [])])
    bocha.search = MagicMock()

    assert service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5) == {}
    assert anspire.search.call_count == 2
    bocha.search.assert_not_called()


def test_stock_physical_failure_falls_back_only_for_failed_group() -> None:
    service = _service(bocha_keys=["bocha-key"])
    anspire = service._anspire_provider
    assert anspire is not None
    bocha = next(provider for provider in service._providers if provider.name == "Bocha")
    anspire.search = MagicMock(
        side_effect=[
            _response("fresh", [], success=False),
            _analysis_response(),
        ]
    )
    bocha.search = MagicMock(
        side_effect=[
            _response("latest", [_item("贵州茅台 600519 最新重大事件", url_suffix="fb-latest")]),
            _response("risk", [_item("贵州茅台 600519 处罚风险", url_suffix="fb-risk")]),
            _response("notice", [_item("贵州茅台 600519 公司公告", url_suffix="fb-notice")]),
        ]
    )

    with patch("src.search_service.time.sleep"):
        results = service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5)

    assert anspire.search.call_count == 2
    assert bocha.search.call_count == 3
    assert set(results) == {
        "latest_news",
        "risk_check",
        "announcements",
        "market_analysis",
        "earnings",
    }


def test_stock_cache_is_shared_across_search_service_instances() -> None:
    first = _service()
    second = _service()
    first_provider = first._anspire_provider
    second_provider = second._anspire_provider
    assert first_provider is not None and second_provider is not None
    first_provider.search = MagicMock(side_effect=[_fresh_response(), _analysis_response()])
    second_provider.search = MagicMock()

    first_results = first.search_comprehensive_intel("600519", "贵州茅台", max_searches=5)
    second_results = second.search_comprehensive_intel("600519", "贵州茅台", max_searches=5)

    assert first_results and second_results
    assert first_provider.search.call_count == 2
    second_provider.search.assert_not_called()


def test_stock_concurrent_cross_instance_cold_start_uses_one_owner_per_group() -> None:
    first = _service()
    second = _service()
    call_count = 0
    call_lock = threading.Lock()

    def search(_query, *, days, **_kwargs):
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.05)
        return _fresh_response() if days == 3 else _analysis_response()

    assert first._anspire_provider is not None and second._anspire_provider is not None
    first._anspire_provider.search = MagicMock(side_effect=search)
    second._anspire_provider.search = MagicMock(side_effect=search)
    barrier = threading.Barrier(2)
    results: list[dict[str, SearchResponse]] = []

    def worker(service: SearchService) -> None:
        barrier.wait(timeout=1)
        results.append(service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5))

    threads = [threading.Thread(target=worker, args=(service,)) for service in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert len(results) == 2
    assert all(result for result in results)
    assert call_count == 2


def test_stock_concurrent_owner_failure_does_not_create_request_storm() -> None:
    first = _service()
    second = _service()
    call_count = 0
    call_lock = threading.Lock()

    def search(query, **_kwargs):
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.05)
        return _response(query, [], success=False)

    assert first._anspire_provider is not None and second._anspire_provider is not None
    first._anspire_provider.search = MagicMock(side_effect=search)
    second._anspire_provider.search = MagicMock(side_effect=search)
    barrier = threading.Barrier(2)
    results: list[dict[str, SearchResponse]] = []

    def worker(service: SearchService) -> None:
        barrier.wait(timeout=1)
        results.append(service.search_comprehensive_intel("600519", "贵州茅台", max_searches=5))

    threads = [threading.Thread(target=worker, args=(service,)) for service in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert results == [{}, {}]
    assert call_count == 2
    assert SearchService._intel_group_inflight == {}

    assert first.search_comprehensive_intel("600519", "贵州茅台", max_searches=5) == {}
    assert call_count == 4


def test_agent_path_keeps_legacy_dimension_requests() -> None:
    service = _service()
    provider = service._anspire_provider
    assert provider is not None
    provider.search = MagicMock(return_value=_response("legacy", []))

    with patch("src.search_service.time.sleep"):
        service.search_comprehensive_intel(
            "600519",
            "贵州茅台",
            max_searches=6,
            call_source="agent",
        )

    assert provider.search.call_count == 6
    assert all("retry_enabled" not in call.kwargs for call in provider.search.call_args_list)
