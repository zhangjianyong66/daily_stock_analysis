import apiClient from './index';
import { toCamelCase } from './utils';
import type { TaskAccepted } from '../types/analysis';
import type {
  ImageImportCommitResponse,
  PositionImageCommitRequest,
  PositionImageParseResponse,
  PortfolioAccountItem,
  PortfolioAccountCreateRequest,
  PortfolioAccountListResponse,
  PortfolioCashLedgerCreateRequest,
  PortfolioCashLedgerListResponse,
  PortfolioCorporateActionCreateRequest,
  PortfolioCorporateActionListResponse,
  PortfolioCostMethod,
  PortfolioDeleteResponse,
  PortfolioEventCreatedResponse,
  PortfolioFxRefreshResponse,
  PortfolioImageDraftUpdateRequest,
  PortfolioImageTaskAccepted,
  PortfolioImageTaskCurrentResponse,
  PortfolioImageTaskSnapshot,
  PortfolioImportBrokerListResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionAnalysisRequest,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
  PortfolioTradeCreateRequest,
  PortfolioTradeListResponse,
  TradeImageCommitRequest,
  TradeImageParseResponse,
} from '../types/portfolio';

type SnapshotQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
  includeRealtime?: boolean;
};

type FxRefreshQuery = {
  accountId?: number;
  asOf?: string;
};

type EventQuery = {
  accountId?: number;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
};

type TradeListQuery = EventQuery & {
  symbol?: string;
  side?: 'buy' | 'sell';
};

type CashListQuery = EventQuery & {
  direction?: 'in' | 'out';
};

type CorporateListQuery = EventQuery & {
  symbol?: string;
  actionType?: 'cash_dividend' | 'split_adjustment';
};

function buildSnapshotParams(query: SnapshotQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  if (query.costMethod) {
    params.cost_method = query.costMethod;
  }
  if (query.includeRealtime !== undefined) {
    params.include_realtime = query.includeRealtime ? 'true' : 'false';
  }
  return params;
}

function buildFxRefreshParams(query: FxRefreshQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  return params;
}

function buildEventParams(query: EventQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.dateFrom) {
    params.date_from = query.dateFrom;
  }
  if (query.dateTo) {
    params.date_to = query.dateTo;
  }
  if (query.page != null) {
    params.page = query.page;
  }
  if (query.pageSize != null) {
    params.page_size = query.pageSize;
  }
  return params;
}

function buildImageImportFormData(
  accountId: number,
  dateField: 'snapshot_date' | 'default_trade_date',
  dateValue: string,
  files: File[],
): FormData {
  const formData = new FormData();
  formData.append('account_id', String(accountId));
  formData.append(dateField, dateValue);
  files.forEach((file) => formData.append('files', file));
  return formData;
}

export const portfolioApi = {
  async getAccounts(includeInactive = false): Promise<PortfolioAccountListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      params: { include_inactive: includeInactive },
    });
    return toCamelCase<PortfolioAccountListResponse>(response.data);
  },

  async createAccount(payload: PortfolioAccountCreateRequest): Promise<PortfolioAccountItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      name: payload.name,
      broker: payload.broker,
      market: payload.market,
      base_currency: payload.baseCurrency,
      owner_id: payload.ownerId,
    });
    return toCamelCase<PortfolioAccountItem>(response.data);
  },

  async deleteAccount(accountId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/accounts/${accountId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async getSnapshot(query: SnapshotQuery = {}): Promise<PortfolioSnapshotResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/snapshot', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioSnapshotResponse>(response.data);
  },

  async analyzePosition(symbol: string, payload: PortfolioPositionAnalysisRequest = {}): Promise<TaskAccepted> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/portfolio/positions/${encodeURIComponent(symbol)}/analysis`,
      {
        account_id: payload.accountId,
        analysis_phase: payload.analysisPhase ?? 'auto',
        force: payload.force ?? false,
      },
    );
    return toCamelCase<TaskAccepted>(response.data);
  },

  async getRisk(query: SnapshotQuery = {}): Promise<PortfolioRiskResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/risk', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioRiskResponse>(response.data);
  },

  async refreshFx(query: FxRefreshQuery = {}): Promise<PortfolioFxRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/fx/refresh', undefined, {
      params: buildFxRefreshParams(query),
    });
    return toCamelCase<PortfolioFxRefreshResponse>(response.data);
  },

  async createTrade(payload: PortfolioTradeCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/trades', {
      account_id: payload.accountId,
      symbol: payload.symbol,
      trade_date: payload.tradeDate,
      trade_time: payload.tradeTime,
      side: payload.side,
      quantity: payload.quantity,
      price: payload.price,
      fee: payload.fee ?? 0,
      tax: payload.tax ?? 0,
      market: payload.market,
      currency: payload.currency,
      trade_uid: payload.tradeUid,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async deleteTrade(tradeId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/trades/${tradeId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async createCashLedger(payload: PortfolioCashLedgerCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', {
      account_id: payload.accountId,
      event_date: payload.eventDate,
      direction: payload.direction,
      amount: payload.amount,
      currency: payload.currency,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async deleteCashLedger(entryId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/cash-ledger/${entryId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async createCorporateAction(payload: PortfolioCorporateActionCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', {
      account_id: payload.accountId,
      symbol: payload.symbol,
      effective_date: payload.effectiveDate,
      action_type: payload.actionType,
      market: payload.market,
      currency: payload.currency,
      cash_dividend_per_share: payload.cashDividendPerShare,
      split_ratio: payload.splitRatio,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async deleteCorporateAction(actionId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/corporate-actions/${actionId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async listTrades(query: TradeListQuery = {}): Promise<PortfolioTradeListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.side) {
      params.side = query.side;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/trades', { params });
    return toCamelCase<PortfolioTradeListResponse>(response.data);
  },

  async listCashLedger(query: CashListQuery = {}): Promise<PortfolioCashLedgerListResponse> {
    const params = buildEventParams(query);
    if (query.direction) {
      params.direction = query.direction;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', { params });
    return toCamelCase<PortfolioCashLedgerListResponse>(response.data);
  },

  async listCorporateActions(query: CorporateListQuery = {}): Promise<PortfolioCorporateActionListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.actionType) {
      params.action_type = query.actionType;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', { params });
    return toCamelCase<PortfolioCorporateActionListResponse>(response.data);
  },

  async listImportBrokers(): Promise<PortfolioImportBrokerListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/imports/csv/brokers');
    return toCamelCase<PortfolioImportBrokerListResponse>(response.data);
  },

  async parseCsvImport(broker: string, file: File): Promise<PortfolioImportParseResponse> {
    const formData = new FormData();
    formData.append('broker', broker);
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toCamelCase<PortfolioImportParseResponse>(response.data);
  },

  async commitCsvImport(
    accountId: number,
    broker: string,
    file: File,
    dryRun = false,
  ): Promise<PortfolioImportCommitResponse> {
    const formData = new FormData();
    formData.append('account_id', String(accountId));
    formData.append('broker', broker);
    formData.append('dry_run', dryRun ? 'true' : 'false');
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/commit', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toCamelCase<PortfolioImportCommitResponse>(response.data);
  },

  async parsePositionImages(
    accountId: number,
    snapshotDate: string,
    files: File[],
  ): Promise<PositionImageParseResponse> {
    const formData = buildImageImportFormData(accountId, 'snapshot_date', snapshotDate, files);
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/portfolio/imports/images/positions/parse',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return toCamelCase<PositionImageParseResponse>(response.data);
  },

  async submitPositionImageTask(
    accountId: number,
    snapshotDate: string,
    files: File[],
  ): Promise<PortfolioImageTaskAccepted> {
    const formData = buildImageImportFormData(accountId, 'snapshot_date', snapshotDate, files);
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/portfolio/imports/images/positions/tasks',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return toCamelCase<PortfolioImageTaskAccepted>(response.data);
  },

  async commitPositionImages(request: PositionImageCommitRequest): Promise<ImageImportCommitResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/portfolio/imports/images/positions/commit',
      {
        batch_id: request.batchId,
        account_id: request.accountId,
        snapshot_date: request.snapshotDate,
        task_id: request.taskId,
        expected_revision: request.expectedRevision,
        positions: request.positions.map((position) => ({
          symbol: position.symbol,
          name: position.name,
          quantity: position.quantity,
          avg_cost: position.avgCost,
        })),
      },
    );
    return toCamelCase<ImageImportCommitResponse>(response.data);
  },

  async parseTradeImages(
    accountId: number,
    defaultTradeDate: string,
    files: File[],
  ): Promise<TradeImageParseResponse> {
    const formData = buildImageImportFormData(accountId, 'default_trade_date', defaultTradeDate, files);
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/portfolio/imports/images/trades/parse',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return toCamelCase<TradeImageParseResponse>(response.data);
  },

  async submitTradeImageTask(
    accountId: number,
    defaultTradeDate: string,
    files: File[],
  ): Promise<PortfolioImageTaskAccepted> {
    const formData = buildImageImportFormData(accountId, 'default_trade_date', defaultTradeDate, files);
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/portfolio/imports/images/trades/tasks',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return toCamelCase<PortfolioImageTaskAccepted>(response.data);
  },

  async commitTradeImages(request: TradeImageCommitRequest): Promise<ImageImportCommitResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/portfolio/imports/images/trades/commit',
      {
        batch_id: request.batchId,
        account_id: request.accountId,
        task_id: request.taskId,
        expected_revision: request.expectedRevision,
        trades: request.trades.map((trade) => ({
          trade_date: trade.tradeDate,
          trade_time: trade.tradeTime,
          symbol: trade.symbol,
          name: trade.name,
          side: trade.side,
          quantity: trade.quantity,
          price: trade.price,
          fee: trade.fee,
          tax: trade.tax,
          trade_uid: trade.tradeUid,
          occurrence_index: trade.occurrenceIndex,
        })),
      },
    );
    return toCamelCase<ImageImportCommitResponse>(response.data);
  },

  async getCurrentImageTask(): Promise<PortfolioImageTaskCurrentResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/imports/images/tasks/current');
    return toCamelCase<PortfolioImageTaskCurrentResponse>(response.data);
  },

  async getImageTask(taskId: string): Promise<PortfolioImageTaskSnapshot> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/portfolio/imports/images/tasks/${encodeURIComponent(taskId)}`,
    );
    return toCamelCase<PortfolioImageTaskSnapshot>(response.data);
  },

  async updateImageTaskDraft(
    taskId: string,
    request: PortfolioImageDraftUpdateRequest,
  ): Promise<PortfolioImageTaskSnapshot> {
    const response = await apiClient.patch<Record<string, unknown>>(
      `/api/v1/portfolio/imports/images/tasks/${encodeURIComponent(taskId)}/draft`,
      {
        expected_revision: request.expectedRevision,
        files: request.files,
        positions: request.positions?.map((position) => ({
          source_refs: position.sourceRefs.map((ref) => ({ file_index: ref.fileIndex, row_index: ref.rowIndex })),
          symbol: position.symbol,
          name: position.name,
          quantity: position.quantity,
          avg_cost: position.avgCost,
          current_price: position.currentPrice,
          market_value: position.marketValue,
          available_quantity: position.availableQuantity,
          weight_pct: position.weightPct,
          profit_loss: position.profitLoss,
          confidence: position.confidence,
          status: position.status,
          issues: position.issues,
        })),
        trades: request.trades?.map((trade) => ({
          source_refs: trade.sourceRefs.map((ref) => ({ file_index: ref.fileIndex, row_index: ref.rowIndex })),
          trade_date: trade.tradeDate,
          trade_time: trade.tradeTime,
          symbol: trade.symbol,
          name: trade.name,
          side: trade.side,
          quantity: trade.quantity,
          price: trade.price,
          fee: trade.fee,
          tax: trade.tax,
          trade_uid: trade.tradeUid,
          confidence: trade.confidence,
          occurrence_index: trade.occurrenceIndex,
          fingerprint: trade.fingerprint,
          dedup_hash: trade.dedupHash,
          status: trade.status,
          issues: trade.issues,
        })),
      },
    );
    return toCamelCase<PortfolioImageTaskSnapshot>(response.data);
  },

  async cancelImageTask(taskId: string): Promise<PortfolioImageTaskSnapshot> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/portfolio/imports/images/tasks/${encodeURIComponent(taskId)}/cancel`,
    );
    return toCamelCase<PortfolioImageTaskSnapshot>(response.data);
  },

  async discardImageTask(taskId: string): Promise<void> {
    await apiClient.delete(`/api/v1/portfolio/imports/images/tasks/${encodeURIComponent(taskId)}`);
  },
};

export function getExistingPortfolioImageTaskId(error: unknown): string | null {
  const response = (error as { response?: { data?: Record<string, unknown> } } | null)?.response;
  const data = response?.data;
  if (!data) return null;
  if (typeof data.existing_task_id === 'string') return data.existing_task_id;
  const detail = data.detail;
  if (detail && typeof detail === 'object' && typeof (detail as Record<string, unknown>).existing_task_id === 'string') {
    return (detail as Record<string, unknown>).existing_task_id as string;
  }
  return null;
}
