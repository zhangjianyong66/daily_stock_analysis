# -*- coding: utf-8 -*-
"""Portfolio API schemas."""

from __future__ import annotations

from datetime import date, time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PortfolioAccountCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    broker: Optional[str] = Field(None, max_length=64)
    market: Literal["cn", "hk", "us", "jp", "kr", "tw"] = "cn"
    base_currency: str = Field("CNY", min_length=3, max_length=8)
    owner_id: Optional[str] = Field(None, max_length=64)


class PortfolioAccountUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    broker: Optional[str] = Field(None, max_length=64)
    market: Optional[Literal["cn", "hk", "us", "jp", "kr", "tw"]] = None
    base_currency: Optional[str] = Field(None, min_length=3, max_length=8)
    owner_id: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None


class PortfolioAccountItem(BaseModel):
    id: int
    owner_id: Optional[str] = None
    name: str
    broker: Optional[str] = None
    market: str
    base_currency: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PortfolioAccountListResponse(BaseModel):
    accounts: List[PortfolioAccountItem] = Field(default_factory=list)


class PortfolioTradeCreateRequest(BaseModel):
    account_id: int
    symbol: str = Field(..., min_length=1, max_length=16)
    trade_date: date
    trade_time: Optional[time] = None
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    fee: float = Field(0.0, ge=0)
    tax: float = Field(0.0, ge=0)
    market: Optional[Literal["cn", "hk", "us", "jp", "kr", "tw"]] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    trade_uid: Optional[str] = Field(None, max_length=128)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioCashLedgerCreateRequest(BaseModel):
    account_id: int
    event_date: date
    direction: Literal["in", "out"]
    amount: float = Field(..., gt=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioCorporateActionCreateRequest(BaseModel):
    account_id: int
    symbol: str = Field(..., min_length=1, max_length=16)
    effective_date: date
    action_type: Literal["cash_dividend", "split_adjustment"]
    market: Optional[Literal["cn", "hk", "us", "jp", "kr", "tw"]] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    cash_dividend_per_share: Optional[float] = Field(None, ge=0)
    split_ratio: Optional[float] = Field(None, gt=0)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioEventCreatedResponse(BaseModel):
    id: int


class PortfolioDeleteResponse(BaseModel):
    deleted: int


class PortfolioTradeListItem(BaseModel):
    id: int
    account_id: int
    trade_uid: Optional[str] = None
    symbol: str
    market: str
    currency: str
    trade_date: str
    trade_time: Optional[str] = None
    side: str
    quantity: float
    price: float
    fee: float
    tax: float
    note: Optional[str] = None
    created_at: Optional[str] = None


class PortfolioTradeListResponse(BaseModel):
    items: List[PortfolioTradeListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PortfolioCashLedgerListItem(BaseModel):
    id: int
    account_id: int
    event_date: str
    direction: str
    amount: float
    currency: str
    note: Optional[str] = None
    created_at: Optional[str] = None


class PortfolioCashLedgerListResponse(BaseModel):
    items: List[PortfolioCashLedgerListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PortfolioCorporateActionListItem(BaseModel):
    id: int
    account_id: int
    symbol: str
    market: str
    currency: str
    effective_date: str
    action_type: str
    cash_dividend_per_share: Optional[float] = None
    split_ratio: Optional[float] = None
    note: Optional[str] = None
    created_at: Optional[str] = None


class PortfolioCorporateActionListResponse(BaseModel):
    items: List[PortfolioCorporateActionListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PortfolioPositionItem(BaseModel):
    symbol: str
    market: str
    currency: str
    quantity: float
    avg_cost: float
    total_cost: float
    last_price: float
    market_value_base: float
    unrealized_pnl_base: float
    unrealized_pnl_pct: Optional[float] = None
    valuation_currency: str
    price_source: str = "unknown"
    price_provider: Optional[str] = None
    price_date: Optional[str] = None
    price_stale: bool = False
    price_available: bool = True
    data_quality: str = "ok"
    limitations: List[str] = Field(default_factory=list)


class PortfolioPositionAnalysisRequest(BaseModel):
    account_id: Optional[int] = Field(None, description="Optional account id; required when a symbol is held in multiple accounts")
    analysis_phase: Literal["auto", "premarket", "intraday", "postmarket"] = "auto"
    force: bool = Field(False, description="Force refresh analysis inputs without bypassing duplicate in-flight tasks")


class PortfolioAccountSnapshot(BaseModel):
    account_id: int
    account_name: str
    owner_id: Optional[str] = None
    broker: Optional[str] = None
    market: str
    base_currency: str
    as_of: str
    cost_method: str
    total_cash: float
    total_market_value: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    fee_total: float
    tax_total: float
    fx_stale: bool
    data_quality: str = "ok"
    limitations: List[str] = Field(default_factory=list)
    positions: List[PortfolioPositionItem] = Field(default_factory=list)


class PortfolioSnapshotResponse(BaseModel):
    as_of: str
    cost_method: str
    currency: str
    account_count: int
    total_cash: float
    total_market_value: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    fee_total: float
    tax_total: float
    fx_stale: bool
    data_quality: str = "ok"
    limitations: List[str] = Field(default_factory=list)
    accounts: List[PortfolioAccountSnapshot] = Field(default_factory=list)


class PortfolioImportTradeItem(BaseModel):
    trade_date: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fee: float
    tax: float
    trade_uid: Optional[str] = None
    dedup_hash: str
    currency: Optional[str] = None


class PortfolioImportParseResponse(BaseModel):
    broker: str
    record_count: int
    skipped_count: int
    error_count: int
    records: List[PortfolioImportTradeItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class PortfolioImportCommitResponse(BaseModel):
    account_id: int
    record_count: int
    inserted_count: int
    duplicate_count: int
    failed_count: int
    dry_run: bool
    errors: List[str] = Field(default_factory=list)


class PortfolioImportBrokerItem(BaseModel):
    broker: str
    aliases: List[str] = Field(default_factory=list)
    display_name: Optional[str] = None


class PortfolioImportBrokerListResponse(BaseModel):
    brokers: List[PortfolioImportBrokerItem] = Field(default_factory=list)


class PortfolioImageFileResult(BaseModel):
    index: int
    filename: Optional[str] = None
    status: Literal["success", "failed"]
    record_count: int = 0
    error: Optional[str] = None


PortfolioImageTaskStatus = Literal[
    "pending",
    "processing",
    "cancel_requested",
    "cancelled",
    "review_required",
    "committing",
    "failed",
]


class PortfolioImageTaskFileItem(BaseModel):
    index: int
    filename: Optional[str] = None
    status: Literal["pending", "processing", "success", "failed", "cancelled"]
    record_count: int = 0
    error: Optional[str] = None
    removed: bool = False


class PortfolioImageTaskAccepted(BaseModel):
    task_id: str
    trace_id: str
    status: PortfolioImageTaskStatus
    mode: Literal["positions", "trades"]
    account_id: int
    account_name: str
    message: str


class PortfolioImageTaskSnapshot(BaseModel):
    task_id: str
    trace_id: str
    mode: Literal["positions", "trades"]
    account_id: int
    account_name: str
    status: PortfolioImageTaskStatus
    message: str
    error_code: Optional[str] = None
    snapshot_date: Optional[str] = None
    default_trade_date: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    files: List[PortfolioImageTaskFileItem] = Field(default_factory=list)
    current_file_index: Optional[int] = None
    total_files: int = 0
    current_attempt: Optional[int] = None
    max_attempts: int = 2
    success_count: int = 0
    failure_count: int = 0
    batch_id: Optional[str] = None
    draft_revision: Optional[int] = None
    draft: Optional[Dict[str, Any]] = None


class PortfolioImageTaskCurrentResponse(BaseModel):
    task: Optional[PortfolioImageTaskSnapshot] = None


class PortfolioImageDraftFileUpdate(BaseModel):
    index: int
    removed: bool = False


class PortfolioImageSourceRef(BaseModel):
    file_index: int
    row_index: int


class PortfolioPositionImageItem(BaseModel):
    source_refs: List[PortfolioImageSourceRef] = Field(default_factory=list)
    symbol: str
    name: str
    quantity: Optional[float] = None
    avg_cost: Optional[float] = None
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    available_quantity: Optional[float] = None
    weight_pct: Optional[float] = None
    profit_loss: Optional[float] = None
    confidence: Literal["high", "medium", "low"] = "low"
    status: Literal["ready", "conflict", "error"]
    issues: List[str] = Field(default_factory=list)


class PortfolioPositionImageParseResponse(BaseModel):
    batch_id: str
    account_id: int
    snapshot_date: str
    files: List[PortfolioImageFileResult] = Field(default_factory=list)
    summary: Dict[str, Optional[float]] = Field(default_factory=dict)
    positions: List[PortfolioPositionImageItem] = Field(default_factory=list)


class PortfolioTradeImageItem(BaseModel):
    source_refs: List[PortfolioImageSourceRef] = Field(default_factory=list)
    trade_date: str
    trade_time: Optional[str] = None
    symbol: str
    name: str
    side: str
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: float = 0
    tax: float = 0
    trade_uid: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "low"
    occurrence_index: int = 1
    fingerprint: str = ""
    dedup_hash: Optional[str] = None
    status: Literal["ready", "conflict", "error"]
    issues: List[str] = Field(default_factory=list)


class PortfolioTradeImageParseResponse(BaseModel):
    batch_id: str
    account_id: int
    default_trade_date: str
    files: List[PortfolioImageFileResult] = Field(default_factory=list)
    trades: List[PortfolioTradeImageItem] = Field(default_factory=list)


class PortfolioImageDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(..., ge=1)
    files: List[PortfolioImageDraftFileUpdate] = Field(default_factory=list)
    positions: Optional[List[PortfolioPositionImageItem]] = None
    trades: Optional[List[PortfolioTradeImageItem]] = None


class PortfolioPositionImageCommitItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., pattern=r"^\d{6}$")
    name: str = Field(..., min_length=1, max_length=64)
    quantity: float = Field(..., gt=0)
    avg_cost: float = Field(..., gt=0)


class PortfolioPositionImageCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(..., min_length=1, max_length=64)
    account_id: int
    snapshot_date: date
    positions: List[PortfolioPositionImageCommitItem] = Field(..., min_length=1)
    task_id: Optional[str] = Field(None, min_length=1, max_length=64)
    expected_revision: Optional[int] = Field(None, ge=1)


class PortfolioTradeImageCommitItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_date: date
    trade_time: Optional[time] = None
    symbol: str = Field(..., pattern=r"^\d{6}$")
    name: Optional[str] = Field(None, max_length=64)
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    fee: float = Field(0, ge=0)
    tax: float = Field(0, ge=0)
    trade_uid: Optional[str] = Field(None, max_length=128)
    occurrence_index: int = Field(1, ge=1)


class PortfolioTradeImageCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(..., min_length=1, max_length=64)
    account_id: int
    trades: List[PortfolioTradeImageCommitItem] = Field(..., min_length=1)
    task_id: Optional[str] = Field(None, min_length=1, max_length=64)
    expected_revision: Optional[int] = Field(None, ge=1)


class PortfolioImageImportCommitResponse(BaseModel):
    record_count: int
    inserted_count: int
    duplicate_count: int
    failed_count: int
    errors: List[str] = Field(default_factory=list)


class PortfolioFxRefreshResponse(BaseModel):
    as_of: str
    account_count: int
    refresh_enabled: bool
    disabled_reason: Optional[str] = None
    pair_count: int
    updated_count: int
    stale_count: int
    error_count: int


class PortfolioDecisionSignalRiskItem(BaseModel):
    account_id: Optional[int] = None
    symbol: str
    market: str
    signal: Dict[str, Any] = Field(default_factory=dict)


class PortfolioDecisionSignalRiskBlock(BaseModel):
    available: bool = True
    total: int = 0
    actions: Dict[str, int] = Field(default_factory=dict)
    items: List[PortfolioDecisionSignalRiskItem] = Field(default_factory=list)


class PortfolioRiskResponse(BaseModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    concentration: Dict[str, Any] = Field(default_factory=dict)
    sector_concentration: Dict[str, Any] = Field(default_factory=dict)
    drawdown: Dict[str, Any] = Field(default_factory=dict)
    stop_loss: Dict[str, Any] = Field(default_factory=dict)
    decision_signal_risk: PortfolioDecisionSignalRiskBlock = Field(default_factory=PortfolioDecisionSignalRiskBlock)
