import pandas as pd
import pytest

from src.agent.tools.analysis_tools import detect_patterns_from_df
from src.services.kline_pattern_service import (
    build_pattern_candidates,
    build_pattern_report,
    build_runtime_pattern_match,
    recommend_pattern_strategies,
)


def _catalog(*names):
    return [{"name": name, "display_name": name, "user_invocable": True} for name in names]


def test_recommendations_are_deterministic_and_filter_unavailable_skills():
    recommendations = recommend_pattern_strategies(
        [{"name": "看跌吞没"}, {"name": "大阴线"}],
        _catalog("emotion_cycle", "volume_breakout", "hidden_skill"),
        language="zh",
    )
    assert [item["skill_id"] for item in recommendations] == ["emotion_cycle"]
    assert recommendations[0]["mode"] == "risk_review"
    assert "进攻性买入" in recommendations[0]["reason"]


def test_pattern_report_keeps_insufficient_data_explicit():
    frame = pd.DataFrame({"open": [1.0] * 5, "high": [1.1] * 5, "low": [0.9] * 5, "close": [1.0] * 5, "volume": [100] * 5})
    report = build_pattern_report("600519", df=frame, skill_catalog=[])
    assert report["schema_version"] == "kline-pattern-v1"
    assert report["status"] == "insufficient_data"
    assert report["recommendations"] == []


def test_pattern_report_uses_saved_shape_and_max_three_recommendations():
    rows = []
    for index in range(60):
        close = 10 + index * 0.01
        rows.append({"open": close - 0.1, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 100})
    frame = pd.DataFrame(rows, index=pd.date_range("2026-01-01", periods=60))
    report = build_pattern_report(
        "600519",
        df=frame,
        source="test",
        skill_catalog=_catalog("volume_breakout", "bull_trend", "box_oscillation", "emotion_cycle"),
    )
    assert report["status"] == "ok"
    assert report["source"] == "test"
    assert len(report["recommendations"]) <= 3


def test_pattern_report_localizes_empty_evidence_summary(monkeypatch):
    frame = pd.DataFrame({
        "open": [1.0] * 10,
        "high": [1.2] * 10,
        "low": [0.8] * 10,
        "close": [1.0] * 10,
        "volume": [100] * 10,
    })
    monkeypatch.setattr(
        "src.services.kline_pattern_service.detect_patterns_from_df",
        lambda *args, **kwargs: {"current_price": 1.0, "patterns": []},
    )

    report = build_pattern_report("600519", language="en", df=frame, skill_catalog=[])

    assert report["summary"] == "Pattern scan completed: Insufficient evidence"


@pytest.mark.parametrize(
    ("pattern", "expected_skill"),
    [
        ("放量突破20日高点", "volume_breakout"),
        ("大阳线", "volume_breakout"),
        ("一阳夹三阴", "one_yang_three_yin"),
        ("缩量回踩", "shrink_pullback"),
        ("早晨之星", "bottom_volume"),
        ("看涨吞没", "bottom_volume"),
        ("双底", "bottom_volume"),
        ("锤子线", "bottom_volume"),
        ("箱体震荡", "box_oscillation"),
        ("黄昏之星", "emotion_cycle"),
        ("看跌吞没", "emotion_cycle"),
        ("流星线", "emotion_cycle"),
        ("上吊线", "emotion_cycle"),
        ("大阴线", "emotion_cycle"),
    ],
)
def test_all_auto_match_rules_share_the_recommendation_mapping(pattern, expected_skill):
    catalog = _catalog(
        "volume_breakout",
        "one_yang_three_yin",
        "shrink_pullback",
        "bottom_volume",
        "box_oscillation",
        "emotion_cycle",
    )
    candidates = build_pattern_candidates(
        [{"name": pattern, "strength": "强", "day_offset": 0}],
        catalog,
    )
    assert candidates[0]["skill_id"] == expected_skill


def test_latest_strong_bearish_reversal_wins_a_bullish_conflict():
    candidates = build_pattern_candidates(
        [
            {"name": "放量突破20日高点", "strength": "强", "day_offset": 0},
            {"name": "看跌吞没", "strength": "强", "day_offset": 0},
        ],
        _catalog("volume_breakout", "emotion_cycle"),
    )
    assert [item["skill_id"] for item in candidates] == ["emotion_cycle", "volume_breakout"]


def test_latest_duplicate_bearish_confirmation_is_used_for_risk_priority():
    candidates = build_pattern_candidates(
        [
            {"name": "看跌吞没", "strength": "强", "day_offset": -4},
            {"name": "放量突破20日高点", "strength": "强", "day_offset": 0},
            {"name": "看跌吞没", "strength": "强", "day_offset": 0},
        ],
        _catalog("volume_breakout", "emotion_cycle"),
    )

    assert candidates[0]["skill_id"] == "emotion_cycle"
    assert candidates[0]["latest_strong_risk"] is True


def test_latest_strong_signal_is_not_overridden_by_an_older_weak_high_priority_rule():
    candidates = build_pattern_candidates(
        [
            {"name": "大阳线", "strength": "弱", "day_offset": -2},
            {"name": "看涨吞没", "strength": "强", "day_offset": 0},
        ],
        _catalog("volume_breakout", "bottom_volume"),
    )
    assert [item["skill_id"] for item in candidates] == ["bottom_volume", "volume_breakout"]


def _daily_frame(count=10, end="2026-07-27"):
    dates = pd.bdate_range(end=end, periods=count)
    return pd.DataFrame(
        {
            "date": dates,
            "open": [10.0] * count,
            "high": [10.5] * count,
            "low": [9.5] * count,
            "close": [10.1] * count,
            "volume": [100.0] * count,
        }
    )


@pytest.mark.parametrize(
    ("target_date", "frame", "reason"),
    [
        (None, _daily_frame(), "calendar_unavailable"),
        ("2026-07-27", _daily_frame(9), "insufficient_data"),
        ("2026-07-28", _daily_frame(), "stale_daily_bars"),
        ("2026-07-27", _daily_frame().drop(columns=["high"]), "invalid_daily_bars"),
    ],
)
def test_runtime_match_has_stable_daily_bar_fallback_reasons(target_date, frame, reason):
    resolution = build_runtime_pattern_match(
        "600519",
        target_date=target_date,
        df=frame,
        skill_catalog=_catalog("box_oscillation"),
    )
    assert resolution.winner is None
    assert resolution.reason_code == reason
    assert resolution.pattern_report["reason_code"] == reason


def test_runtime_match_reports_unavailable_candidate_without_reloading(monkeypatch):
    calls = 0

    def fake_detect(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "current_price": 10.1,
            "patterns": [{"pattern": "缩量回踩", "type": "bullish_continuation", "strength": "中", "day_offset": 0}],
        }

    monkeypatch.setattr("src.services.kline_pattern_service.detect_patterns_from_df", fake_detect)
    resolution = build_runtime_pattern_match(
        "600519",
        target_date="2026-07-27",
        df=_daily_frame(),
        skill_catalog=[],
    )
    assert calls == 1
    assert resolution.reason_code == "candidate_unavailable"
    assert resolution.pattern_report["reason_code"] == "candidate_unavailable"


def test_one_yang_three_yin_reads_only_the_latest_five_bars():
    rows = [
        {"open": 10.0, "high": 10.3, "low": 9.8, "close": 10.1, "volume": 100.0}
        for _ in range(55)
    ]
    rows.extend(
        [
            {"open": 10.0, "high": 12.2, "low": 9.9, "close": 12.0, "volume": 200.0},
            {"open": 12.0, "high": 12.1, "low": 11.7, "close": 11.8, "volume": 100.0},
            {"open": 11.8, "high": 11.9, "low": 11.5, "close": 11.6, "volume": 90.0},
            {"open": 11.6, "high": 11.7, "low": 11.3, "close": 11.4, "volume": 80.0},
            {"open": 11.4, "high": 12.7, "low": 11.3, "close": 12.5, "volume": 180.0},
        ]
    )
    detected = detect_patterns_from_df(pd.DataFrame(rows), "600519")
    pattern = next(item for item in detected["patterns"] if item["pattern"] == "一阳夹三阴")
    assert pattern["day_offset"] == 0

    shifted = rows[-5:] + rows[:-5]
    shifted_detected = detect_patterns_from_df(pd.DataFrame(shifted), "600519")
    assert all(item["pattern"] != "一阳夹三阴" for item in shifted_detected["patterns"])
