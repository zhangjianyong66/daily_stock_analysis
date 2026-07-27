import pandas as pd

from src.services.kline_pattern_service import build_pattern_report, recommend_pattern_strategies


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
