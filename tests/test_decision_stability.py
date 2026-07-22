# -*- coding: utf-8 -*-
"""Tests for structure-aware decision stability calibration."""

from types import SimpleNamespace

from src.analyzer import (
    AnalysisResult,
    _capital_flow_bias,
    _etf_risk_reward_plan,
    stabilize_decision_with_structure,
)
from src.utils.sniper_points import parse_sniper_value


def _result(
    *,
    decision_type: str,
    operation_advice: str,
    score: int,
    current_price: float,
    change_pct: float = 0.0,
    code: str = "002812",
) -> AnalysisResult:
    return AnalysisResult(
        code=code,
        name="恩捷股份",
        sentiment_score=score,
        trend_prediction="看多" if decision_type == "buy" else "看空",
        operation_advice=operation_advice,
        decision_type=decision_type,
        report_language="zh",
        current_price=current_price,
        change_pct=change_pct,
        dashboard={
            "core_conclusion": {"one_sentence": "原始结论"},
            "data_perspective": {
                "price_position": {
                    "current_price": current_price,
                    "support_level": 30.0,
                    "resistance_level": 34.0,
                }
            },
        },
    )


def _fund_flow(main: float, five_day: float = 0.0, ten_day: float = 0.0) -> dict:
    return {
        "capital_flow": {
            "status": "ok",
            "data": {
                "stock_flow": {
                    "main_net_inflow": main,
                    "inflow_5d": five_day,
                    "inflow_10d": ten_day,
                }
            },
        }
    }


def _unsupported_fund_flow() -> dict:
    return {"capital_flow": {"status": "not_supported", "data": {}}}


def _unsupported_fund_flow_caps() -> dict:
    return {"capital_flow": {"status": "NOT_SUPPORTED", "data": {"stock_flow": {"main_net_inflow": 0}}}}


def _etf_fund_flow(
    *,
    latest: float,
    previous: float,
    latest_pct: float,
    previous_pct: float,
    inflow_3d: float,
    positive_days_3d: int,
    inflow_5d: float,
    as_of: str = "2026-07-21",
    intraday_net: float = 0.0,
) -> dict:
    return {
        "capital_flow": {
            "status": "ok",
            "data": {
                "stock_flow": {
                    "main_net_inflow": latest,
                    "main_net_inflow_pct": latest_pct,
                    "previous_main_net_inflow": previous,
                    "previous_main_net_inflow_pct": previous_pct,
                    "inflow_3d": inflow_3d,
                    "positive_days_3d": positive_days_3d,
                    "inflow_5d": inflow_5d,
                    "inflow_10d": inflow_5d,
                    "as_of": as_of,
                    "scope": "daily",
                },
                "intraday_flow": {
                    "active_net_inflow": intraday_net,
                    "scope": "intraday",
                    "classification": "vendor_classified",
                    "is_estimated": True,
                },
            },
        }
    }


def _phase(effective_date: str = "2026-07-21") -> dict:
    return {"effective_daily_bar_date": effective_date, "phase": "premarket"}


def test_capital_flow_bias_is_unavailable_when_stock_flow_data_is_missing() -> None:
    assert _capital_flow_bias(_unsupported_fund_flow()) == "unavailable"
    assert _capital_flow_bias({"capital_flow": {"status": "ok", "data": {}}}) == "unavailable"


def test_capital_flow_bias_is_neutral_when_missing_main_windows_conflict() -> None:
    context = {
        "capital_flow": {
            "data": {
                "stock_flow": {
                    "inflow_5d": 2_000_000,
                    "inflow_10d": -1_000_000,
                }
            }
        }
    }

    assert _capital_flow_bias(context) == "neutral"


def test_capital_flow_bias_is_neutral_when_main_conflicts_with_windows() -> None:
    context = _fund_flow(main=-500_000, five_day=1_200_000, ten_day=2_000_000)

    assert _capital_flow_bias(context) == "neutral"


def test_downgrades_buy_near_resistance_without_fund_confirmation() -> None:
    result = _result(
        decision_type="buy",
        operation_advice="买入",
        score=65,
        current_price=33.4,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=-1_000_000, five_day=-2_000_000),
    )

    assert result.decision_type == "hold"
    assert result.sentiment_score <= 59
    assert result.operation_advice == "震荡观望"
    assert result.dashboard["decision_stability"]["applied"] is True
    assert "不宜仅因短线反弹追买" in result.risk_warning
    assert result.dashboard["core_conclusion"]["signal_type"] == "🟡持有观望"


def test_downgrades_buy_mid_range_with_neutral_fund_flow() -> None:
    result = _result(
        decision_type="buy",
        operation_advice="买入",
        score=66,
        current_price=32.0,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=0, five_day=0, ten_day=0),
    )

    assert result.decision_type == "hold"
    assert result.sentiment_score <= 59
    assert result.operation_advice == "震荡观望"
    assert "资金流不明确" in result.risk_warning


def test_downgrades_buy_when_capital_flow_is_unavailable() -> None:
    buy_result = _result(
        decision_type="buy",
        operation_advice="买入",
        score=66,
        current_price=32.0,
    )
    sell_result = _result(
        decision_type="sell",
        operation_advice="卖出",
        score=30,
        current_price=30.4,
        change_pct=-2.1,
    )

    stabilize_decision_with_structure(
        buy_result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _unsupported_fund_flow(),
    )
    stabilize_decision_with_structure(
        sell_result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _unsupported_fund_flow(),
    )

    assert buy_result.decision_type == "hold"
    assert buy_result.operation_advice == "持有观察"
    assert buy_result.confidence_level == "低"
    assert buy_result.sentiment_score <= 59
    assert buy_result.dashboard["decision_stability"]["applied"] is True
    assert "买入结论缺少资金面确认" in buy_result.dashboard["decision_stability"]["reason"]
    assert buy_result.dashboard["core_conclusion"]["signal_type"] == "🟡持有观望"
    assert sell_result.decision_type == "sell"
    assert sell_result.operation_advice == "卖出"
    assert sell_result.dashboard["decision_stability"]["applied"] is False
    assert "未使用资金流校准" in sell_result.dashboard["decision_stability"]["reason"]


def test_downgrades_buy_when_capital_flow_values_are_na() -> None:
    result = _result(
        decision_type="buy",
        operation_advice="买入",
        score=66,
        current_price=33.0,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        {
            "capital_flow": {
                "status": "ok",
                "data": {
                    "stock_flow": {
                        "main_net_inflow": "N/A",
                        "inflow_5d": "N/A",
                        "inflow_10d": "N/A",
                    }
                },
            }
        },
    )

    assert result.decision_type == "hold"
    assert result.operation_advice == "持有观察"
    assert result.dashboard["decision_stability"]["applied"] is True
    assert "资金流数据缺失" in result.dashboard["decision_stability"]["capital_flow_status"]


def test_downgrades_buy_advice_when_decision_type_is_hold_and_capital_flow_unavailable() -> None:
    result = _result(
        decision_type="hold",
        operation_advice="建议买入",
        score=68,
        current_price=32.0,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _unsupported_fund_flow(),
    )

    assert result.decision_type == "hold"
    assert result.operation_advice == "持有观察"
    assert result.sentiment_score <= 59
    assert result.dashboard["decision_stability"]["applied"] is True
    assert "买入结论缺少资金面确认" in result.dashboard["decision_stability"]["reason"]


def test_downgrades_buy_when_capital_flow_status_is_unavailable_case_insensitive() -> None:
    buy_result = _result(
        decision_type="buy",
        operation_advice="买入",
        score=66,
        current_price=32.0,
    )

    stabilize_decision_with_structure(
        buy_result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _unsupported_fund_flow_caps(),
    )

    assert buy_result.decision_type == "hold"
    assert buy_result.operation_advice == "持有观察"
    assert buy_result.dashboard["decision_stability"]["applied"] is True
    assert "暂不支持" in str(buy_result.dashboard["decision_stability"]["capital_flow_status"])


def test_skips_downgrade_when_only_generic_risk_warning_and_sell_near_support() -> None:
    result = _result(
        decision_type="sell",
        operation_advice="卖出",
        score=30,
        current_price=30.4,
        change_pct=1.0,
    )
    result.risk_warning = "注意常见回撤风险，建议关注仓位。"

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=500_000, five_day=300_000),
    )

    assert result.decision_type == "hold"
    assert result.operation_advice == "洗盘观察"
    assert "价格贴近支撑且未见资金持续流出" in result.risk_warning


def test_stability_can_infer_decision_from_natural_chinese_phrases_in_analyzer_path() -> None:
    result = _result(
        decision_type="建议卖出",
        operation_advice="建议卖出",
        score=30,
        current_price=30.4,
        change_pct=1.0,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=500_000, five_day=300_000),
    )

    assert result.decision_type == "hold"
    assert result.operation_advice == "洗盘观察"
    assert result.dashboard["decision_stability"]["applied"] is True


def test_downgrades_sell_near_support_without_sustained_outflow() -> None:
    result = _result(
        decision_type="sell",
        operation_advice="卖出",
        score=30,
        current_price=30.4,
        change_pct=-2.1,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=800_000, five_day=1_200_000),
    )

    assert result.decision_type == "hold"
    assert result.sentiment_score >= 45
    assert result.operation_advice == "洗盘观察"
    assert "不宜仅因单日下跌直接卖出" in result.risk_warning


def test_preserves_sell_signal_when_significant_risk_exists_near_support() -> None:
    result = _result(
        decision_type="sell",
        operation_advice="卖出",
        score=30,
        current_price=30.4,
        change_pct=-2.1,
    )
    result.risk_warning = "重大利空消息：公司发布重大减持计划"
    result.dashboard["intelligence"] = {"risk_alerts": ["股东高位减持预告"]}

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=800_000, five_day=1_200_000),
    )

    assert result.decision_type == "sell"
    assert result.operation_advice == "卖出"


def test_refines_hold_pullback_near_support_as_shakeout_watch() -> None:
    result = _result(
        decision_type="hold",
        operation_advice="持有",
        score=52,
        current_price=30.5,
        change_pct=-1.6,
    )

    stabilize_decision_with_structure(
        result,
        SimpleNamespace(support_levels=[30.0], resistance_levels=[34.0]),
        _fund_flow(main=0, five_day=500_000),
    )

    assert result.decision_type == "hold"
    assert result.operation_advice == "洗盘观察"
    assert "更适合按洗盘观察处理" in result.risk_warning


def test_etf_oversold_with_improving_flow_allows_only_starter_position() -> None:
    result = _result(
        code="159865",
        decision_type="hold",
        operation_advice="观望",
        score=35,
        current_price=10.1,
    )
    trend = SimpleNamespace(
        current_price=10.1,
        ma5=10.5,
        bias_ma5=-3.81,
        rsi_12=31.0,
        change_3d=-5.0,
        is_new_low_3d=False,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=-500_000,
            previous=-1_000_000,
            latest_pct=-2.0,
            previous_pct=-4.2,
            inflow_3d=-1_200_000,
            positive_days_3d=1,
            inflow_5d=-2_000_000,
        ),
        _phase(),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["strategy_state"] == "starter_entry"
    assert 60 <= result.sentiment_score <= 69
    assert result.decision_type == "buy"
    assert strategy["position_cap_pct"] == 30
    assert "20%-30%试仓" in result.operation_advice
    assert "未提供真实成本" in result.dashboard["core_conclusion"]["position_advice"]["has_position"]
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert sniper["ideal_buy"].startswith("计划试仓触发价：10.1元")
    assert "确认加仓参考位：10.5元" in sniper["secondary_buy"]
    assert "有效止损位" in sniper["stop_loss"]
    assert "第一止盈位" in sniper["take_profit"]
    assert parse_sniper_value(sniper["ideal_buy"]) == strategy["risk_reward"]["entry_price"]
    assert parse_sniper_value(sniper["secondary_buy"]) == 10.5
    assert parse_sniper_value(sniper["stop_loss"]) == strategy["risk_reward"]["effective_stop_price"]
    assert parse_sniper_value(sniper["take_profit"]) == strategy["risk_reward"]["minimum_target_price"]


def test_etf_oversold_but_new_low_and_outflow_stays_watch_only() -> None:
    result = _result(
        code="512480",
        decision_type="buy",
        operation_advice="买入",
        score=88,
        current_price=9.9,
    )
    trend = SimpleNamespace(
        current_price=9.9,
        ma5=10.4,
        bias_ma5=-4.81,
        rsi_12=29.0,
        change_3d=-6.0,
        is_new_low_3d=True,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=-1_200_000,
            previous=-800_000,
            latest_pct=-5.0,
            previous_pct=-3.0,
            inflow_3d=-2_500_000,
            positive_days_3d=0,
            inflow_5d=-4_000_000,
            intraday_net=99_000_000,
        ),
        _phase(),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["strategy_state"] == "oversold_watch"
    assert result.decision_type == "hold"
    assert result.sentiment_score == 59
    assert strategy["intraday_flow_used_for_score"] is False
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert "当前不执行买入" in sniper["ideal_buy"]
    assert "确认加仓观察位" in sniper["secondary_buy"]


def test_etf_single_oversold_indicator_cannot_trigger_starter_entry() -> None:
    result = _result(
        code="159865",
        decision_type="buy",
        operation_advice="买入",
        score=90,
        current_price=10.1,
    )
    trend = SimpleNamespace(
        current_price=10.1,
        ma5=10.2,
        bias_ma5=-0.98,
        rsi_12=30.0,
        change_3d=-1.0,
        is_new_low_3d=False,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=500_000,
            previous=-500_000,
            latest_pct=2.0,
            previous_pct=-2.0,
            inflow_3d=800_000,
            positive_days_3d=2,
            inflow_5d=1_000_000,
        ),
        _phase(),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["oversold_signal_count"] == 1
    assert strategy["strategy_state"] == "neutral_watch"
    assert result.decision_type == "hold"
    assert result.sentiment_score == 59


def test_etf_missing_new_low_confirmation_stays_watch_only() -> None:
    result = _result(
        code="159865",
        decision_type="buy",
        operation_advice="买入",
        score=90,
        current_price=10.1,
    )
    trend = SimpleNamespace(
        current_price=10.1,
        ma5=10.5,
        bias_ma5=-3.81,
        rsi_12=31.0,
        change_3d=-5.0,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=-500_000,
            previous=-1_000_000,
            latest_pct=-2.0,
            previous_pct=-4.2,
            inflow_3d=-1_200_000,
            positive_days_3d=1,
            inflow_5d=-2_000_000,
        ),
        _phase(),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["strategy_state"] == "oversold_watch"
    assert strategy["stopped_falling"] is False
    assert result.decision_type == "hold"


def test_etf_confirmed_flow_and_ma5_reclaim_allows_add_on() -> None:
    result = _result(
        code="561510",
        decision_type="hold",
        operation_advice="观望",
        score=45,
        current_price=10.0,
    )
    trend = SimpleNamespace(
        current_price=10.0,
        ma5=9.9,
        bias_ma5=1.01,
        rsi_12=32.0,
        change_3d=-4.5,
        is_new_low_3d=False,
        support_levels=[9.9],
        resistance_levels=[10.3],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=600_000,
            previous=-200_000,
            latest_pct=2.5,
            previous_pct=-0.5,
            inflow_3d=900_000,
            positive_days_3d=2,
            inflow_5d=1_100_000,
        ),
        _phase(),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["strategy_state"] == "add_on_confirmation"
    assert 70 <= result.sentiment_score <= 79
    assert result.action == "add"
    assert strategy["position_cap_pct"] == 60
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert "确认入场参考价" in sniper["ideal_buy"]
    assert "确认加仓参考位" in sniper["secondary_buy"]
    assert "仓位上限40%-60%" in sniper["secondary_buy"]


def test_etf_high_bias_overbought_near_resistance_forces_full_exit() -> None:
    result = _result(
        code="513050",
        decision_type="buy",
        operation_advice="买入",
        score=92,
        current_price=10.8,
    )
    trend = SimpleNamespace(
        current_price=10.8,
        ma5=10.3,
        bias_ma5=4.85,
        rsi_12=70.0,
        change_3d=5.0,
        is_new_low_3d=False,
        support_levels=[10.2],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(result, trend, _unsupported_fund_flow(), _phase())

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["strategy_state"] == "take_profit_exit"
    assert result.sentiment_score == 19
    assert result.decision_type == "sell"
    assert strategy["position_cap_pct"] == 0
    assert "全额退出" in result.operation_advice
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert "暂停买入参考价" in sniper["ideal_buy"]
    assert "当前不执行加仓" in sniper["secondary_buy"]
    assert "当前高抛退出优先" in sniper["stop_loss"]
    assert "当前按全额退出执行" in sniper["take_profit"]


def test_etf_invalidated_sniper_points_cancel_entry_and_target() -> None:
    result = _result(
        code="159865",
        decision_type="buy",
        operation_advice="买入",
        score=82,
        current_price=9.7,
    )
    trend = SimpleNamespace(
        current_price=9.7,
        ma5=10.1,
        bias_ma5=-3.96,
        rsi_12=42.0,
        change_3d=-2.0,
        is_new_low_3d=True,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(result, trend, _unsupported_fund_flow(), _phase())

    strategy = result.dashboard["etf_short_term_strategy"]
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert strategy["strategy_state"] == "invalidated"
    assert "暂停买入参考价" in sniper["ideal_buy"]
    assert "结构已失效" in sniper["stop_loss"]
    assert "目标作废" in sniper["take_profit"]


def test_etf_sniper_points_explain_missing_levels_without_fake_prices() -> None:
    result = _result(
        code="159865",
        decision_type="hold",
        operation_advice="观望",
        score=50,
        current_price=1.23456,
    )
    price_position = result.dashboard["data_perspective"]["price_position"]
    price_position["support_level"] = None
    price_position["resistance_level"] = None
    trend = SimpleNamespace(
        current_price=1.23456,
        ma5=None,
        bias_ma5=0.0,
        rsi_12=50.0,
        change_3d=0.0,
        is_new_low_3d=False,
        support_levels=[],
        resistance_levels=[],
    )

    stabilize_decision_with_structure(result, trend, _unsupported_fund_flow(), _phase())

    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert sniper["ideal_buy"].startswith("观察触发参考价：1.2346元")
    assert parse_sniper_value(sniper["ideal_buy"]) == 1.2346
    assert "暂无确认加仓参考位" in sniper["secondary_buy"]
    assert "暂无有效止损位" in sniper["stop_loss"]
    assert "暂无有效止盈位" in sniper["take_profit"]
    assert parse_sniper_value(sniper["secondary_buy"]) is None
    assert parse_sniper_value(sniper["stop_loss"]) is None
    assert parse_sniper_value(sniper["take_profit"]) is None


def test_etf_sniper_points_preserve_parseable_prices_in_english_report() -> None:
    result = _result(
        code="159865",
        decision_type="hold",
        operation_advice="Watch",
        score=35,
        current_price=10.1,
    )
    result.report_language = "en"
    trend = SimpleNamespace(
        current_price=10.1,
        ma5=10.5,
        bias_ma5=-3.81,
        rsi_12=31.0,
        change_3d=-5.0,
        is_new_low_3d=False,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=-500_000,
            previous=-1_000_000,
            latest_pct=-2.0,
            previous_pct=-4.2,
            inflow_3d=-1_200_000,
            positive_days_3d=1,
            inflow_5d=-2_000_000,
        ),
        _phase(),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    sniper = result.dashboard["battle_plan"]["sniper_points"]
    assert sniper["ideal_buy"].startswith("Starter trigger: 10.1 CNY")
    assert "MA5 add-on confirmation: 10.5 CNY" in sniper["secondary_buy"]
    assert parse_sniper_value(sniper["ideal_buy"]) == strategy["risk_reward"]["entry_price"]
    assert parse_sniper_value(sniper["secondary_buy"]) == 10.5
    assert parse_sniper_value(sniper["stop_loss"]) == strategy["risk_reward"]["effective_stop_price"]
    assert parse_sniper_value(sniper["take_profit"]) == strategy["risk_reward"]["minimum_target_price"]


def test_etf_stale_daily_flow_cannot_trigger_starter_entry() -> None:
    result = _result(
        code="159865",
        decision_type="buy",
        operation_advice="买入",
        score=80,
        current_price=10.1,
    )
    trend = SimpleNamespace(
        current_price=10.1,
        ma5=10.5,
        bias_ma5=-3.81,
        rsi_12=31.0,
        change_3d=-5.0,
        is_new_low_3d=False,
        support_levels=[10.0],
        resistance_levels=[11.0],
    )

    stabilize_decision_with_structure(
        result,
        trend,
        _etf_fund_flow(
            latest=500_000,
            previous=-500_000,
            latest_pct=2.0,
            previous_pct=-2.0,
            inflow_3d=800_000,
            positive_days_3d=2,
            inflow_5d=1_000_000,
            as_of="2026-07-18",
        ),
        _phase("2026-07-21"),
    )

    strategy = result.dashboard["etf_short_term_strategy"]
    assert strategy["strategy_state"] == "oversold_watch"
    assert strategy["daily_capital_flow"]["is_fresh"] is False
    assert result.decision_type == "hold"


def test_etf_structure_stop_over_3pct_rejects_entry() -> None:
    plan = _etf_risk_reward_plan(entry_price=10.3, support=9.8, resistance=12.0)

    assert plan["valid"] is False
    assert plan["invalid_reason"] == "structure_stop_distance_exceeds_3pct"


def test_etf_risk_reward_requires_at_least_exactly_1_5r() -> None:
    reference = _etf_risk_reward_plan(entry_price=10.0, support=9.9, resistance=12.0)
    exact_target = reference["minimum_target_price"]

    exact = _etf_risk_reward_plan(entry_price=10.0, support=9.9, resistance=exact_target)
    below = _etf_risk_reward_plan(entry_price=10.0, support=9.9, resistance=exact_target - 0.0002)

    assert exact["valid"] is True
    assert exact["reward_risk_ratio"] >= 1.5
    assert below["valid"] is False
    assert below["invalid_reason"] == "first_resistance_below_1_5r"
