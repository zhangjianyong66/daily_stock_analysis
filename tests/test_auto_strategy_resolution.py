from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from src.agent.factory import SkillPromptState
from src.agent.skills.base import Skill, SkillManager
from src.core.pipeline import StockAnalysisPipeline
from src.schemas.strategy_execution import build_strategy_execution_snapshot
from src.services.kline_pattern_service import PatternMatchResolution


def _prompt_state():
    manager = SkillManager()
    for name in ("bull_trend", "volume_breakout", "box_oscillation"):
        manager.register(
            Skill(
                name=name,
                display_name=name,
                description=name,
                instructions=f"instructions:{name}",
                source="builtin",
            )
        )
    manager.activate(["bull_trend"])
    return SkillPromptState(
        skill_manager=manager,
        skills_to_activate=["bull_trend"],
        explicit_skill_selection=False,
        use_legacy_default_prompt=True,
        skill_instructions=manager.get_skill_instructions(),
        default_skill_policy="default",
        technical_skill_policy="technical",
        strategy_execution=build_strategy_execution_snapshot(
            effective=[{"id": "bull_trend", "display_name": "bull_trend"}],
            source="default",
        ),
        selection_source="builtin",
        default_skill_id="bull_trend",
        default_skill_source="builtin",
        saved_default_skill_id="",
        default_skill_warning=None,
    )


def _pipeline():
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.config = SimpleNamespace(report_language="zh")
    pipeline.analysis_skills = None
    pipeline.skill_prompt_state = _prompt_state()
    return pipeline


def _match(skill_id, pattern):
    candidate = {
        "skill_id": skill_id,
        "display_name": skill_id,
        "matched_patterns": [pattern],
        "mode": "analysis",
        "strength_rank": 3,
        "day_offset": 0,
        "rule_priority": 10,
        "latest_strong_risk": False,
    }
    return PatternMatchResolution(
        pattern_report={"status": "ok", "as_of": "2026-07-27", "patterns": [], "recommendations": []},
        candidates=(candidate,),
        winner=candidate,
        reason_code=None,
        matched_patterns=(pattern,),
    )


def test_two_concurrent_stocks_keep_independent_auto_prompt_states(monkeypatch):
    pipeline = _pipeline()
    monkeypatch.setattr("src.core.pipeline.get_reliable_effective_trading_date", lambda *args, **kwargs: "2026-07-27")
    monkeypatch.setattr(
        "src.services.kline_pattern_service.build_runtime_pattern_match",
        lambda code, **kwargs: (
            _match("volume_breakout", "大阳线")
            if code == "600519"
            else _match("box_oscillation", "箱体震荡")
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(
            lambda code: pipeline._resolve_stock_strategy(code, current_time=None),
            ("600519", "000001"),
        )

    assert first.skills == ("volume_breakout",)
    assert second.skills == ("box_oscillation",)
    assert [skill.name for skill in first.prompt_state.skill_manager.list_active_skills()] == ["volume_breakout"]
    assert [skill.name for skill in second.prompt_state.skill_manager.list_active_skills()] == ["box_oscillation"]
    assert [skill.name for skill in pipeline.skill_prompt_state.skill_manager.list_active_skills()] == ["bull_trend"]


def test_auto_match_failure_uses_the_frozen_fallback_and_context(monkeypatch):
    pipeline = _pipeline()
    monkeypatch.setattr("src.core.pipeline.get_reliable_effective_trading_date", lambda *args, **kwargs: "2026-07-27")
    monkeypatch.setattr(
        "src.services.kline_pattern_service.build_runtime_pattern_match",
        lambda *args, **kwargs: PatternMatchResolution(
            pattern_report={"status": "ok", "as_of": "2026-07-27", "patterns": [], "recommendations": []},
            candidates=(),
            winner=None,
            reason_code="no_reliable_pattern",
        ),
    )

    resolution = pipeline._resolve_stock_strategy("600519", current_time=None)

    assert resolution.mode == "fallback"
    assert resolution.skills == ("bull_trend",)
    assert resolution.prompt_state.strategy_execution["source"] == "fallback"
    assert resolution.prompt_state.strategy_execution["selection_context"]["fallback_reason"] == "no_reliable_pattern"


def test_explicit_strategy_is_not_replaced_by_auto_match(monkeypatch):
    pipeline = _pipeline()
    pipeline.analysis_skills = ["box_oscillation"]
    pipeline.skill_prompt_state = _prompt_state()
    pipeline.skill_prompt_state.skill_manager.activate(["box_oscillation"])
    pipeline.skill_prompt_state.skills_to_activate = ["box_oscillation"]
    monkeypatch.setattr("src.core.pipeline.get_reliable_effective_trading_date", lambda *args, **kwargs: "2026-07-27")
    def _unexpected_auto_match(*args, **kwargs):
        raise AssertionError("explicit strategy must not run daily-bar auto matching")

    monkeypatch.setattr(
        "src.services.kline_pattern_service.build_runtime_pattern_match",
        _unexpected_auto_match,
    )

    resolution = pipeline._resolve_stock_strategy("600519", current_time=None)

    assert resolution.mode == "explicit"
    assert resolution.skills == ("box_oscillation",)
    assert resolution.selection_context is None


def test_auto_resolution_does_not_use_saved_fallback_to_force_agent_mode():
    pipeline = _pipeline()
    pipeline.config.agent_mode = False
    pipeline.skill_prompt_state.selection_source = "saved"

    assert pipeline._should_use_agent_for_strategy_resolution(
        SimpleNamespace(mode="matched"), code="600519", stock_name="first"
    ) is False
    assert pipeline._should_use_agent_for_strategy_resolution(
        SimpleNamespace(mode="fallback"), code="000001", stock_name="second"
    ) is False
    assert pipeline._should_use_agent_for_strategy_resolution(
        None, code="600519", stock_name="legacy"
    ) is True
