# -*- coding: utf-8 -*-
"""Portfolio endpoints (P0 core account + snapshot workflow)."""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from api.v1.errors import api_error
from api.v1.schemas.analysis import DuplicateTaskErrorResponse, TaskAccepted
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio import (
    PortfolioAccountCreateRequest,
    PortfolioAccountItem,
    PortfolioAccountListResponse,
    PortfolioAccountUpdateRequest,
    PortfolioCashLedgerListResponse,
    PortfolioCashLedgerCreateRequest,
    PortfolioCorporateActionListResponse,
    PortfolioCorporateActionCreateRequest,
    PortfolioDeleteResponse,
    PortfolioEventCreatedResponse,
    PortfolioFxRefreshResponse,
    PortfolioImportBrokerListResponse,
    PortfolioImportCommitResponse,
    PortfolioImportParseResponse,
    PortfolioImportTradeItem,
    PortfolioImageImportCommitResponse,
    PortfolioImageDraftUpdateRequest,
    PortfolioImageTaskAccepted,
    PortfolioImageTaskCurrentResponse,
    PortfolioImageTaskSnapshot,
    PortfolioPositionImageCommitRequest,
    PortfolioPositionImageParseResponse,
    PortfolioTradeImageCommitRequest,
    PortfolioTradeImageParseResponse,
    PortfolioPositionAnalysisRequest,
    PortfolioRiskResponse,
    PortfolioSnapshotResponse,
    PortfolioTradeListResponse,
    PortfolioTradeCreateRequest,
)
from src.services.task_queue import get_task_queue
from src.services.portfolio_image_task_manager import (
    PortfolioImageDraftConflictError,
    PortfolioImageTaskActiveError,
    PortfolioImageTaskError,
    PortfolioImageTaskNotFoundError,
    get_portfolio_image_task_manager,
)
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_risk_service import PortfolioRiskService
from src.services.portfolio_screenshot_import_service import (
    AccountNotEmptyError,
    AmbiguousTradeOrderError,
    ImageInput,
    PortfolioScreenshotImportService,
)
from src.services.portfolio_service import (
    PortfolioBusyError,
    PortfolioConflictError,
    PortfolioOversellError,
    PortfolioService,
)
from src.services.vision_extraction_service import VisionExtractionError

logger = logging.getLogger(__name__)

router = APIRouter()


def _bad_request(exc: Exception) -> HTTPException:
    return api_error(400, "validation_error", str(exc))


def _internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error(f"{message}: {exc}", exc_info=True)
    return api_error(500, "internal_error", f"{message}: {str(exc)}")


def _conflict_error(*, error: str, message: str) -> HTTPException:
    return api_error(409, error, message)


def _screenshot_internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error("%s (%s)", message, type(exc).__name__, exc_info=True)
    return api_error(500, "internal_error", message)


def _portfolio_image_task_http_error(exc: PortfolioImageTaskError) -> HTTPException:
    if isinstance(exc, PortfolioImageTaskNotFoundError):
        return api_error(404, exc.code, str(exc))
    detail = None
    if isinstance(exc, PortfolioImageDraftConflictError):
        detail = {"current_revision": exc.current_revision}
    elif isinstance(exc, PortfolioImageTaskActiveError):
        detail = {
            "existing_task_id": exc.existing_task_id,
            "existing_status": exc.existing_status,
        }
    return api_error(409, exc.code, str(exc), detail=detail)


def _active_image_task_response(exc: PortfolioImageTaskActiveError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": exc.code,
            "message": str(exc),
            "existing_task_id": exc.existing_task_id,
            "existing_status": exc.existing_status,
        },
    )


async def _read_image_inputs(files: List[UploadFile]) -> List[ImageInput]:
    if len(files) > 5:
        raise api_error(400, "too_many_files", "A screenshot batch supports at most 5 files")
    if not files:
        raise api_error(400, "validation_error", "At least one screenshot is required")
    images: List[ImageInput] = []
    for file in files:
        images.append(
            ImageInput(
                content=await file.read(5 * 1024 * 1024 + 1),
                mime_type=file.content_type or "application/octet-stream",
                filename=file.filename,
            )
        )
    return images


def _serialize_import_record(item: dict) -> PortfolioImportTradeItem:
    payload = dict(item)
    trade_date = payload.get("trade_date")
    if isinstance(trade_date, date):
        payload["trade_date"] = trade_date.isoformat()
    else:
        payload["trade_date"] = str(trade_date)
    return PortfolioImportTradeItem(**payload)


@router.post(
    "/accounts",
    response_model=PortfolioAccountItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create portfolio account",
)
def create_account(request: PortfolioAccountCreateRequest) -> PortfolioAccountItem:
    service = PortfolioService()
    try:
        row = service.create_account(
            name=request.name,
            broker=request.broker,
            market=request.market,
            base_currency=request.base_currency,
            owner_id=request.owner_id,
        )
        return PortfolioAccountItem(**row)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create account failed", exc)


@router.get(
    "/accounts",
    response_model=PortfolioAccountListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List portfolio accounts",
)
def list_accounts(
    include_inactive: bool = Query(False, description="Whether to include inactive accounts"),
) -> PortfolioAccountListResponse:
    service = PortfolioService()
    try:
        rows = service.list_accounts(include_inactive=include_inactive)
        return PortfolioAccountListResponse(accounts=[PortfolioAccountItem(**item) for item in rows])
    except Exception as exc:
        raise _internal_error("List accounts failed", exc)


@router.put(
    "/accounts/{account_id}",
    response_model=PortfolioAccountItem,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Update portfolio account",
)
def update_account(account_id: int, request: PortfolioAccountUpdateRequest) -> PortfolioAccountItem:
    service = PortfolioService()
    try:
        updated = service.update_account(
            account_id,
            name=request.name,
            broker=request.broker,
            market=request.market,
            base_currency=request.base_currency,
            owner_id=request.owner_id,
            is_active=request.is_active,
        )
        if updated is None:
            raise api_error(404, "not_found", f"Account not found: {account_id}")
        return PortfolioAccountItem(**updated)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Update account failed", exc)


@router.delete(
    "/accounts/{account_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Deactivate portfolio account",
)
def delete_account(account_id: int):
    service = PortfolioService()
    try:
        ok = service.deactivate_account(account_id)
        if not ok:
            raise api_error(404, "not_found", f"Account not found: {account_id}")
        return {"deleted": 1}
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Deactivate account failed", exc)


@router.post(
    "/trades",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record trade event",
)
def create_trade(request: PortfolioTradeCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_trade(
            account_id=request.account_id,
            symbol=request.symbol,
            trade_date=request.trade_date,
            trade_time=request.trade_time,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            fee=request.fee,
            tax=request.tax,
            market=request.market,
            currency=request.currency,
            trade_uid=request.trade_uid,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except PortfolioOversellError as exc:
        raise _conflict_error(error="portfolio_oversell", message=str(exc))
    except PortfolioConflictError as exc:
        raise _conflict_error(error="conflict", message=str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create trade failed", exc)


@router.get(
    "/trades",
    response_model=PortfolioTradeListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List trade events",
)
def list_trades(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Trade date from"),
    date_to: Optional[date] = Query(None, description="Trade date to"),
    symbol: Optional[str] = Query(None, description="Optional stock symbol filter"),
    side: Optional[str] = Query(None, description="Optional side filter: buy/sell"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioTradeListResponse:
    service = PortfolioService()
    try:
        data = service.list_trade_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol,
            side=side,
            page=page,
            page_size=page_size,
        )
        return PortfolioTradeListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List trade events failed", exc)


@router.delete(
    "/trades/{trade_id}",
    response_model=PortfolioDeleteResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Delete trade event",
)
def delete_trade(trade_id: int) -> PortfolioDeleteResponse:
    service = PortfolioService()
    try:
        ok = service.delete_trade_event(trade_id)
        if not ok:
            raise api_error(404, "not_found", f"Trade not found: {trade_id}")
        return PortfolioDeleteResponse(deleted=1)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Delete trade event failed", exc)


@router.post(
    "/cash-ledger",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record cash event",
)
def create_cash_ledger(request: PortfolioCashLedgerCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_cash_ledger(
            account_id=request.account_id,
            event_date=request.event_date,
            direction=request.direction,
            amount=request.amount,
            currency=request.currency,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create cash ledger event failed", exc)


@router.get(
    "/cash-ledger",
    response_model=PortfolioCashLedgerListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List cash ledger events",
)
def list_cash_ledger(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Cash event date from"),
    date_to: Optional[date] = Query(None, description="Cash event date to"),
    direction: Optional[str] = Query(None, description="Optional direction filter: in/out"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioCashLedgerListResponse:
    service = PortfolioService()
    try:
        data = service.list_cash_ledger_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            direction=direction,
            page=page,
            page_size=page_size,
        )
        return PortfolioCashLedgerListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List cash ledger events failed", exc)


@router.delete(
    "/cash-ledger/{entry_id}",
    response_model=PortfolioDeleteResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Delete cash ledger event",
)
def delete_cash_ledger(entry_id: int) -> PortfolioDeleteResponse:
    service = PortfolioService()
    try:
        ok = service.delete_cash_ledger_event(entry_id)
        if not ok:
            raise api_error(404, "not_found", f"Cash ledger entry not found: {entry_id}")
        return PortfolioDeleteResponse(deleted=1)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Delete cash ledger event failed", exc)


@router.post(
    "/corporate-actions",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record corporate action event",
)
def create_corporate_action(request: PortfolioCorporateActionCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_corporate_action(
            account_id=request.account_id,
            symbol=request.symbol,
            effective_date=request.effective_date,
            action_type=request.action_type,
            market=request.market,
            currency=request.currency,
            cash_dividend_per_share=request.cash_dividend_per_share,
            split_ratio=request.split_ratio,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create corporate action event failed", exc)


@router.get(
    "/corporate-actions",
    response_model=PortfolioCorporateActionListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List corporate action events",
)
def list_corporate_actions(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Corporate action effective date from"),
    date_to: Optional[date] = Query(None, description="Corporate action effective date to"),
    symbol: Optional[str] = Query(None, description="Optional stock symbol filter"),
    action_type: Optional[str] = Query(None, description="Optional action type filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioCorporateActionListResponse:
    service = PortfolioService()
    try:
        data = service.list_corporate_action_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol,
            action_type=action_type,
            page=page,
            page_size=page_size,
        )
        return PortfolioCorporateActionListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List corporate action events failed", exc)


@router.delete(
    "/corporate-actions/{action_id}",
    response_model=PortfolioDeleteResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Delete corporate action event",
)
def delete_corporate_action(action_id: int) -> PortfolioDeleteResponse:
    service = PortfolioService()
    try:
        ok = service.delete_corporate_action_event(action_id)
        if not ok:
            raise api_error(404, "not_found", f"Corporate action not found: {action_id}")
        return PortfolioDeleteResponse(deleted=1)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Delete corporate action event failed", exc)


@router.get(
    "/snapshot",
    response_model=PortfolioSnapshotResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get portfolio snapshot",
)
def get_snapshot(
    account_id: Optional[int] = Query(None, description="Optional account id, default returns all accounts"),
    as_of: Optional[date] = Query(None, description="Snapshot date, default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
    include_realtime: bool = Query(
        True,
        description="Whether today's snapshot should try realtime quotes before historical close fallback",
    ),
) -> PortfolioSnapshotResponse:
    service = PortfolioService()
    try:
        data = service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            include_realtime=include_realtime,
        )
        return PortfolioSnapshotResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get snapshot failed", exc)


@router.post(
    "/positions/{symbol}/analysis",
    status_code=202,
    response_model=TaskAccepted,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": DuplicateTaskErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Submit manual analysis for a held portfolio position",
)
def analyze_position(symbol: str, request: PortfolioPositionAnalysisRequest) -> TaskAccepted | JSONResponse:
    service = PortfolioService()
    try:
        context = _resolve_position_analysis_context(service, symbol=symbol, account_id=request.account_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Resolve portfolio position failed", exc)

    queue = get_task_queue()
    accepted, duplicates = queue.submit_tasks_batch(
        [context["symbol"]],
        stock_name=None,
        original_query=context["symbol"],
        selection_source="manual",
        query_source="portfolio",
        portfolio_context=context,
        report_type="detailed",
        analysis_phase=request.analysis_phase,
        force_refresh=bool(request.force),
        notify=True,
    )
    if duplicates:
        dup = duplicates[0]
        error_response = DuplicateTaskErrorResponse(
            error="duplicate_task",
            message=str(dup),
            stock_code=dup.stock_code,
            existing_task_id=dup.existing_task_id,
        )
        return JSONResponse(status_code=409, content=error_response.model_dump())
    task = accepted[0]
    response = TaskAccepted(
        task_id=task.task_id,
        trace_id=task.trace_id or task.task_id,
        status="pending",
        message=f"分析任务已加入队列: {task.stock_code}",
        analysis_phase=task.analysis_phase,
    )
    return response


def _resolve_position_analysis_context(
    service: PortfolioService,
    *,
    symbol: str,
    account_id: Optional[int],
) -> dict:
    target = service._normalize_symbol_for_position(symbol)
    if not target:
        raise ValueError("symbol must not be empty")

    snapshot = service.get_portfolio_snapshot(account_id=account_id, cost_method="fifo")
    matches = []
    for account in snapshot.get("accounts") or []:
        for position in account.get("positions") or []:
            position_symbol = service._normalize_symbol_for_position(
                str(position.get("symbol") or "")
            )
            if position_symbol != target:
                continue
            try:
                quantity = float(position.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            if quantity <= 0:
                continue
            matches.append((account, position, position_symbol))

    if not matches:
        raise api_error(404, "not_found", f"No non-zero portfolio position for {target}")
    if account_id is None:
        account_ids = {
            int(account.get("account_id"))
            for account, _, _ in matches
            if account.get("account_id") is not None
        }
        if len(account_ids) > 1:
            raise api_error(
                400,
                "ambiguous_position_account",
                f"{target} is held in multiple accounts; pass account_id",
            )

    account, position, position_symbol = matches[0]
    return {
        "account_id": account.get("account_id"),
        "account_name": account.get("account_name"),
        "symbol": position_symbol or target,
        "market": position.get("market"),
        "currency": position.get("currency"),
        "quantity": position.get("quantity"),
        "avg_cost": position.get("avg_cost"),
        "total_cost": position.get("total_cost"),
        "unrealized_pnl_base": position.get("unrealized_pnl_base"),
        "unrealized_pnl_pct": position.get("unrealized_pnl_pct"),
        "price_source": position.get("price_source"),
        "price_provider": position.get("price_provider"),
        "price_date": position.get("price_date"),
        "price_stale": bool(position.get("price_stale")),
        "price_available": bool(position.get("price_available", True)),
        "cost_method": snapshot.get("cost_method") or "fifo",
    }


def _accepted_image_task(snapshot: dict) -> PortfolioImageTaskAccepted:
    return PortfolioImageTaskAccepted(**snapshot)


@router.post(
    "/imports/images/positions/tasks",
    status_code=202,
    response_model=PortfolioImageTaskAccepted,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Submit an asynchronous position screenshot task",
)
async def submit_position_image_task(
    account_id: int = Form(...),
    snapshot_date: date = Form(...),
    files: List[UploadFile] = File(...),
) -> PortfolioImageTaskAccepted | JSONResponse:
    service = PortfolioScreenshotImportService()
    try:
        images = await _read_image_inputs(files)
        snapshot = get_portfolio_image_task_manager().submit_task(
            mode="positions",
            account_id=account_id,
            date_value=snapshot_date,
            images=images,
            service=service,
        )
        return _accepted_image_task(snapshot)
    except PortfolioImageTaskActiveError as exc:
        return _active_image_task_response(exc)
    except HTTPException:
        raise
    except VisionExtractionError as exc:
        raise api_error(400, exc.code, str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _screenshot_internal_error("Submit position screenshot task failed", exc)


@router.post(
    "/imports/images/trades/tasks",
    status_code=202,
    response_model=PortfolioImageTaskAccepted,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Submit an asynchronous executed-trade screenshot task",
)
async def submit_trade_image_task(
    account_id: int = Form(...),
    default_trade_date: date = Form(...),
    files: List[UploadFile] = File(...),
) -> PortfolioImageTaskAccepted | JSONResponse:
    service = PortfolioScreenshotImportService()
    try:
        images = await _read_image_inputs(files)
        snapshot = get_portfolio_image_task_manager().submit_task(
            mode="trades",
            account_id=account_id,
            date_value=default_trade_date,
            images=images,
            service=service,
        )
        return _accepted_image_task(snapshot)
    except PortfolioImageTaskActiveError as exc:
        return _active_image_task_response(exc)
    except HTTPException:
        raise
    except VisionExtractionError as exc:
        raise api_error(400, exc.code, str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _screenshot_internal_error("Submit trade screenshot task failed", exc)


@router.get(
    "/imports/images/tasks/current",
    response_model=PortfolioImageTaskCurrentResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get the current portfolio image task",
)
def get_current_image_task() -> PortfolioImageTaskCurrentResponse:
    return PortfolioImageTaskCurrentResponse(task=get_portfolio_image_task_manager().get_current_task())


@router.get(
    "/imports/images/tasks/{task_id}",
    response_model=PortfolioImageTaskSnapshot,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get a portfolio image task",
)
def get_image_task(task_id: str) -> PortfolioImageTaskSnapshot:
    try:
        return PortfolioImageTaskSnapshot(**get_portfolio_image_task_manager().get_task(task_id))
    except PortfolioImageTaskError as exc:
        raise _portfolio_image_task_http_error(exc)


@router.patch(
    "/imports/images/tasks/{task_id}/draft",
    response_model=PortfolioImageTaskSnapshot,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Replace the reviewed portfolio image draft",
)
def update_image_task_draft(
    task_id: str,
    request: PortfolioImageDraftUpdateRequest,
) -> PortfolioImageTaskSnapshot:
    try:
        snapshot = get_portfolio_image_task_manager().update_draft(
            task_id,
            expected_revision=request.expected_revision,
            files=[item.model_dump() for item in request.files],
            positions=[item.model_dump() for item in request.positions] if request.positions is not None else None,
            trades=[item.model_dump() for item in request.trades] if request.trades is not None else None,
        )
        return PortfolioImageTaskSnapshot(**snapshot)
    except PortfolioImageTaskError as exc:
        raise _portfolio_image_task_http_error(exc)


@router.post(
    "/imports/images/tasks/{task_id}/cancel",
    response_model=PortfolioImageTaskSnapshot,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Request cancellation of a running portfolio image task",
)
def cancel_image_task(task_id: str) -> PortfolioImageTaskSnapshot:
    try:
        return PortfolioImageTaskSnapshot(**get_portfolio_image_task_manager().cancel_task(task_id))
    except PortfolioImageTaskError as exc:
        raise _portfolio_image_task_http_error(exc)


@router.delete(
    "/imports/images/tasks/{task_id}",
    response_model=PortfolioDeleteResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Discard or clear a portfolio image task",
)
def discard_image_task(task_id: str) -> PortfolioDeleteResponse:
    try:
        get_portfolio_image_task_manager().discard_task(task_id)
        return PortfolioDeleteResponse(deleted=1)
    except PortfolioImageTaskError as exc:
        raise _portfolio_image_task_http_error(exc)


@router.post(
    "/imports/images/positions/parse",
    response_model=PortfolioPositionImageParseResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse position screenshots for user review",
    deprecated=True,
)
async def parse_position_images(
    account_id: int = Form(...),
    snapshot_date: date = Form(...),
    files: List[UploadFile] = File(...),
) -> PortfolioPositionImageParseResponse | JSONResponse:
    service = PortfolioScreenshotImportService()
    try:
        images = await _read_image_inputs(files)
        result = await run_in_threadpool(
            get_portfolio_image_task_manager().run_sync_parse,
            mode="positions",
            account_id=account_id,
            date_value=snapshot_date,
            images=images,
            service=service,
        )
        return PortfolioPositionImageParseResponse(**result)
    except PortfolioImageTaskActiveError as exc:
        return _active_image_task_response(exc)
    except PortfolioImageTaskError as exc:
        raise _portfolio_image_task_http_error(exc)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _screenshot_internal_error("Parse position screenshots failed", exc)


@router.post(
    "/imports/images/trades/parse",
    response_model=PortfolioTradeImageParseResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse executed-trade screenshots for user review",
    deprecated=True,
)
async def parse_trade_images(
    account_id: int = Form(...),
    default_trade_date: date = Form(...),
    files: List[UploadFile] = File(...),
) -> PortfolioTradeImageParseResponse | JSONResponse:
    service = PortfolioScreenshotImportService()
    try:
        images = await _read_image_inputs(files)
        result = await run_in_threadpool(
            get_portfolio_image_task_manager().run_sync_parse,
            mode="trades",
            account_id=account_id,
            date_value=default_trade_date,
            images=images,
            service=service,
        )
        return PortfolioTradeImageParseResponse(**result)
    except PortfolioImageTaskActiveError as exc:
        return _active_image_task_response(exc)
    except PortfolioImageTaskError as exc:
        raise _portfolio_image_task_http_error(exc)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _screenshot_internal_error("Parse trade screenshots failed", exc)


@router.post(
    "/imports/images/positions/commit",
    response_model=PortfolioImageImportCommitResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Atomically initialize positions from reviewed screenshots",
)
def commit_position_images(
    request: PortfolioPositionImageCommitRequest,
) -> PortfolioImageImportCommitResponse:
    service = PortfolioScreenshotImportService()
    task_manager = get_portfolio_image_task_manager()
    commit_started = False
    try:
        if request.task_id:
            task_manager.begin_commit(
                request.task_id,
                mode="positions",
                account_id=request.account_id,
                batch_id=request.batch_id,
                expected_revision=request.expected_revision,
                date_value=request.snapshot_date,
            )
            commit_started = True
        else:
            task_manager.ensure_legacy_commit_allowed()
        result = service.commit_initial_positions(
            account_id=request.account_id,
            batch_id=request.batch_id,
            snapshot_date=request.snapshot_date,
            positions=[item.model_dump() for item in request.positions],
        )
        if commit_started and request.task_id:
            task_manager.finish_commit(request.task_id)
        return PortfolioImageImportCommitResponse(**result)
    except PortfolioImageTaskError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _portfolio_image_task_http_error(exc)
    except AccountNotEmptyError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _conflict_error(error="account_not_empty", message=str(exc))
    except PortfolioBusyError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except ValueError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _bad_request(exc)
    except Exception as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _screenshot_internal_error("Commit position screenshots failed", exc)


@router.post(
    "/imports/images/trades/commit",
    response_model=PortfolioImageImportCommitResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Atomically import reviewed executed trades",
)
def commit_trade_images(
    request: PortfolioTradeImageCommitRequest,
) -> PortfolioImageImportCommitResponse:
    service = PortfolioScreenshotImportService()
    task_manager = get_portfolio_image_task_manager()
    commit_started = False
    try:
        if request.task_id:
            task_manager.begin_commit(
                request.task_id,
                mode="trades",
                account_id=request.account_id,
                batch_id=request.batch_id,
                expected_revision=request.expected_revision,
            )
            commit_started = True
        else:
            task_manager.ensure_legacy_commit_allowed()
        result = service.commit_trade_batch(
            account_id=request.account_id,
            batch_id=request.batch_id,
            trades=[item.model_dump() for item in request.trades],
        )
        if commit_started and request.task_id:
            task_manager.finish_commit(request.task_id)
        return PortfolioImageImportCommitResponse(**result)
    except PortfolioImageTaskError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _portfolio_image_task_http_error(exc)
    except AmbiguousTradeOrderError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _conflict_error(error="ambiguous_trade_order", message=str(exc))
    except PortfolioOversellError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _conflict_error(error="portfolio_oversell", message=str(exc))
    except PortfolioBusyError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except ValueError as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _bad_request(exc)
    except Exception as exc:
        if commit_started and request.task_id:
            task_manager.rollback_commit(request.task_id)
        raise _screenshot_internal_error("Commit trade screenshots failed", exc)


@router.post(
    "/imports/csv/parse",
    response_model=PortfolioImportParseResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse broker CSV into normalized trade records",
)
def parse_csv_import(
    broker: str = Form(..., description="Broker id: huatai/citic/cmb"),
    file: UploadFile = File(...),
) -> PortfolioImportParseResponse:
    importer = PortfolioImportService()
    try:
        content = file.file.read()
        parsed = importer.parse_trade_csv(broker=broker, content=content)
        return PortfolioImportParseResponse(
            broker=parsed["broker"],
            record_count=parsed["record_count"],
            skipped_count=parsed["skipped_count"],
            error_count=parsed["error_count"],
            records=[_serialize_import_record(item) for item in parsed.get("records", [])],
            errors=list(parsed.get("errors", [])),
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Parse CSV import failed", exc)


@router.get(
    "/imports/csv/brokers",
    response_model=PortfolioImportBrokerListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List supported broker CSV parsers",
)
def list_csv_brokers() -> PortfolioImportBrokerListResponse:
    importer = PortfolioImportService()
    try:
        return PortfolioImportBrokerListResponse(brokers=importer.list_supported_brokers())
    except Exception as exc:
        raise _internal_error("List CSV brokers failed", exc)


@router.post(
    "/imports/csv/commit",
    response_model=PortfolioImportCommitResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse and commit broker CSV with dedup",
)
def commit_csv_import(
    account_id: int = Form(...),
    broker: str = Form(..., description="Broker id: huatai/citic/cmb"),
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
) -> PortfolioImportCommitResponse:
    importer = PortfolioImportService()
    try:
        content = file.file.read()
        parsed = importer.parse_trade_csv(broker=broker, content=content)
        result = importer.commit_trade_records(
            account_id=account_id,
            broker=parsed["broker"],
            records=list(parsed.get("records", [])),
            dry_run=dry_run,
        )
        return PortfolioImportCommitResponse(**result)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Commit CSV import failed", exc)


@router.post(
    "/fx/refresh",
    response_model=PortfolioFxRefreshResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Refresh FX cache online with stale fallback",
)
def refresh_fx_rates(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Rate date, default today"),
) -> PortfolioFxRefreshResponse:
    service = PortfolioService()
    try:
        data = service.refresh_fx_rates(account_id=account_id, as_of=as_of)
        return PortfolioFxRefreshResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Refresh FX rates failed", exc)


@router.get(
    "/risk",
    response_model=PortfolioRiskResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get portfolio risk report",
)
def get_risk_report(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Risk report date, default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
    include_realtime: bool = Query(
        True,
        description="Whether today's risk snapshot should try realtime quotes before historical close fallback",
    ),
) -> PortfolioRiskResponse:
    service = PortfolioRiskService()
    try:
        data = service.get_risk_report(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            include_realtime=include_realtime,
        )
        return PortfolioRiskResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get risk report failed", exc)
