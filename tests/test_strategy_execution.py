from types import SimpleNamespace

from api.v1.endpoints.analysis import _build_analysis_report
from src.agent import factory
from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import AgentContext
from src.agent.skills.base import Skill, SkillManager
from src.analyzer import AnalysisResult
from src.schemas.strategy_execution import (
    build_strategy_execution_snapshot,
    format_strategy_execution_text,
    localize_strategy_execution,
    normalize_strategy_execution,
)


def _skill_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(Skill(
        name="bull_trend",
        display_name="默认多头趋势",
        description="趋势分析",
        instructions="遵循多头趋势。",
        source="builtin",
        default_active=True,
        default_router=True,
    ))
    manager.register(Skill(
        name="box_oscillation",
        display_name="箱体震荡",
        description="震荡分析",
        instructions="遵循箱体震荡。",
        source="builtin",
    ))
    return manager


def test_strategy_execution_snapshot_preserves_effective_and_rejected_strategies():
    snapshot = build_strategy_execution_snapshot(
        requested=[{"id": "removed_skill", "display_name": "旧策略"}],
        effective=[{"id": "bull_trend", "display_name": "趋势策略"}],
        source="fallback",
        status="fallback",
        rejected=[{"id": "removed_skill", "reason": "unavailable"}],
    )

    assert normalize_strategy_execution(snapshot) == snapshot
    assert snapshot["effective"][0]["display_name"] == "趋势策略"
    assert snapshot["rejected"] == [{"id": "removed_skill", "reason": "unavailable"}]


def test_missing_strategy_execution_is_rendered_as_unrecorded_instead_of_inferred():
    text = format_strategy_execution_text(None, "zh")

    assert "分析策略：策略未记录" in text
    assert "未保存策略信息" in text


def test_invalid_strategy_execution_is_not_treated_as_historical_fact():
    assert normalize_strategy_execution({
        "schema_version": 1,
        "status": "unexpected",
        "source": "default",
        "effective": [{"id": "bull_trend", "display_name": "趋势策略"}],
    }) is None


def test_analysis_result_persists_strategy_execution_in_raw_result():
    snapshot = build_strategy_execution_snapshot(
        effective=[{"id": "bull_trend", "display_name": "趋势策略"}],
        source="default",
    )
    result = AnalysisResult(
        code="600519",
        name="贵州茅台",
        sentiment_score=50,
        trend_prediction="震荡",
        operation_advice="观望",
        strategy_execution=snapshot,
    )

    assert result.to_dict()["strategy_execution"] == snapshot


def test_builtin_strategy_name_is_localized_for_api_display():
    snapshot = build_strategy_execution_snapshot(
        effective=[{"id": "bull_trend", "display_name": "趋势策略"}],
        source="default",
    )

    localized = localize_strategy_execution(snapshot, "en")

    assert localized is not None
    assert localized["effective"][0]["id"] == "bull_trend"
    assert localized["effective"][0]["display_name"]


def test_factory_records_request_fallback_and_partial_execution(monkeypatch):
    monkeypatch.setattr(factory, "get_skill_manager", lambda _config: _skill_manager())
    config = SimpleNamespace(agent_skills=[])

    fallback = factory.resolve_skill_prompt_state(config, skills=["removed_skill"]).strategy_execution
    partial = factory.resolve_skill_prompt_state(
        config,
        skills=["box_oscillation", "removed_skill"],
    ).strategy_execution

    assert fallback["status"] == "fallback"
    assert fallback["source"] == "fallback"
    assert fallback["effective"][0]["id"] == "bull_trend"
    assert fallback["requested"][0]["status"] == "not_executed"
    assert partial["status"] == "partial"
    assert partial["source"] == "request"
    assert [item["id"] for item in partial["effective"]] == ["box_oscillation"]


def test_factory_distinguishes_default_and_fixed_config_sources(monkeypatch):
    monkeypatch.setattr(factory, "get_skill_manager", lambda _config: _skill_manager())

    default_snapshot = factory.resolve_skill_prompt_state(
        SimpleNamespace(agent_skills=[]),
    ).strategy_execution
    config_snapshot = factory.resolve_skill_prompt_state(
        SimpleNamespace(agent_skills=["box_oscillation"]),
    ).strategy_execution

    assert default_snapshot["source"] == "default"
    assert config_snapshot["source"] == "config"


def test_saved_default_precedes_agent_skills_and_explicit_request_precedes_saved_default(monkeypatch):
    monkeypatch.setattr(factory, "get_skill_manager", lambda _config: _skill_manager())
    config = SimpleNamespace(
        default_analysis_skill="box_oscillation",
        agent_skills=["bull_trend"],
    )

    saved_state = factory.resolve_skill_prompt_state(config)
    request_state = factory.resolve_skill_prompt_state(config, skills=["bull_trend"])

    assert saved_state.skills_to_activate == ["box_oscillation"]
    assert saved_state.selection_source == "saved"
    assert saved_state.strategy_execution["source"] == "config"
    assert saved_state.strategy_execution["effective"][0]["id"] == "box_oscillation"
    assert request_state.skills_to_activate == ["bull_trend"]
    assert request_state.selection_source == "request"
    assert request_state.strategy_execution["source"] == "request"


def test_unavailable_saved_default_falls_back_to_agent_skills_with_warning(monkeypatch):
    monkeypatch.setattr(factory, "get_skill_manager", lambda _config: _skill_manager())
    config = SimpleNamespace(
        default_analysis_skill="removed_skill",
        agent_skills=["box_oscillation"],
    )

    resolution = factory.resolve_default_skill_selection(config)
    state = factory.resolve_skill_prompt_state(config)

    assert resolution.effective_ids == ["box_oscillation"]
    assert resolution.public_source == "fallback"
    assert resolution.saved_default_skill_id == "removed_skill"
    assert resolution.warning
    assert state.strategy_execution["status"] == "fallback"
    assert state.strategy_execution["source"] == "fallback"
    assert state.strategy_execution["requested"][0]["id"] == "removed_skill"
    assert state.strategy_execution["rejected"] == [
        {"id": "removed_skill", "reason": "unavailable"}
    ]


def test_orchestrator_records_auto_routing_and_strategy_degradation():
    orchestrator = object.__new__(AgentOrchestrator)
    orchestrator.config = SimpleNamespace(agent_skill_routing="auto")
    orchestrator.skill_manager = _skill_manager()
    orchestrator.strategy_execution = build_strategy_execution_snapshot(
        effective=[{"id": "bull_trend", "display_name": "默认多头趋势"}],
        source="default",
    )
    context = AgentContext(query="分析")

    orchestrator._record_routed_strategies(context, ["box_oscillation"])
    orchestrator._mark_strategy_degraded("skill_box_oscillation")

    assert orchestrator.strategy_execution["source"] == "auto"
    assert orchestrator.strategy_execution["status"] == "degraded"
    assert orchestrator.strategy_execution["effective"][0]["status"] == "degraded"


def test_analysis_report_api_reads_strategy_execution_from_persisted_raw_result():
    snapshot = build_strategy_execution_snapshot(
        effective=[{"id": "box_oscillation", "display_name": "箱体震荡"}],
        source="request",
    )

    report = _build_analysis_report(
        {
            "meta": {"stock_code": "600519", "report_language": "zh"},
            "summary": {"analysis_summary": "测试报告"},
        },
        "query-1",
        "600519",
        fallback_raw_result_payload={"strategy_execution": snapshot},
    )

    assert report.meta.strategy_execution is not None
    assert report.meta.strategy_execution.source == "request"
    assert report.meta.strategy_execution.effective[0].id == "box_oscillation"
