import apiClient from './index';
import { toCamelCase } from './utils';

export type UsagePeriod = 'today' | 'month' | 'all';
export type SearchUsagePeriod = 'today' | '7d' | 'month' | 'all' | 'custom';

export type UsageCallTypeBreakdown = {
  callType: string;
  calls: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
};

export type UsageModelBreakdown = {
  model: string;
  calls: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  maxTotalTokens: number;
};

export type UsageCallRecord = {
  id: number;
  calledAt: string;
  callType: string;
  model: string;
  stockCode?: string | null;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
};

export type UsageDashboard = {
  period: UsagePeriod;
  fromDate: string;
  toDate: string;
  totalCalls: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  byCallType: UsageCallTypeBreakdown[];
  byModel: UsageModelBreakdown[];
  recentCalls: UsageCallRecord[];
};

export type SearchUsageFilters = {
  period?: SearchUsagePeriod;
  fromTime?: string;
  toTime?: string;
  provider?: string;
  source?: string;
  success?: boolean;
  errorCategory?: string;
  keyFingerprint?: string;
  page?: number;
  pageSize?: number;
};

export type SearchUsageBreakdown = { value: string; count: number };
export type SearchAuditHealth = {
  healthy: boolean;
  processLostCount: number;
  persistedLostCount: number;
  lastGapAt?: string | null;
};
export type SearchProviderFault = {
  id: number;
  provider: string;
  keyFingerprint: string;
  errorCategory: string;
  active: boolean;
  severity: string;
  firstSeenAt: string;
  lastSeenAt: string;
  lastErrorSummary?: string | null;
  lastCallId?: number | null;
};
export type SearchProviderStatus = {
  provider: string;
  status: 'normal' | 'degraded' | 'unavailable';
  configuredKeys: number;
  failedKeys: number;
};
export type SearchFaultStatus = {
  activeFaults: SearchProviderFault[];
  providers: SearchProviderStatus[];
  auditHealth: SearchAuditHealth;
};
export type SearchUsageCall = {
  id: number;
  businessSearchId: string;
  logicalRequestId: string;
  provider: string;
  endpoint: string;
  httpMethod: string;
  callSource: string;
  operation: string;
  stockCode?: string | null;
  stockName?: string | null;
  dimension?: string | null;
  lookbackDays?: number | null;
  providerAttempt: number;
  physicalAttempt: number;
  keyFingerprint: string;
  success: boolean;
  httpStatus?: number | null;
  providerCode?: string | null;
  providerRequestId?: string | null;
  durationMs: number;
  resultCount?: number | null;
  errorCategory?: string | null;
  errorSummary?: string | null;
  requestTruncated: boolean;
  requestSizeBytes: number;
  requestSha256: string;
  responseTruncated: boolean;
  responseSizeBytes: number;
  responseSha256: string;
  requestedAt: string;
  completedAt: string;
};
export type SearchUsageCallDetail = SearchUsageCall & {
  traceId?: string | null;
  queryHmac?: string | null;
  requestSnapshot: unknown;
  responseSnapshot: unknown;
};
export type SearchUsageDashboard = {
  auditStartedAt?: string | null;
  summary: {
    physicalRequests: number;
    businessSearches: number;
    successCount: number;
    failureCount: number;
    successRate: number;
  };
  byProvider: SearchUsageBreakdown[];
  byKey: SearchUsageBreakdown[];
  bySource: SearchUsageBreakdown[];
  calls: { items: SearchUsageCall[]; total: number; page: number; pageSize: number };
  faults: SearchFaultStatus;
  auditHealth: SearchAuditHealth;
};

function searchParams(params: SearchUsageFilters) {
  return {
    period: params.period ?? 'month',
    from_time: params.fromTime || undefined,
    to_time: params.toTime || undefined,
    provider: params.provider || undefined,
    source: params.source || undefined,
    success: params.success,
    error_category: params.errorCategory || undefined,
    key_fingerprint: params.keyFingerprint || undefined,
    page: params.page ?? 1,
    page_size: params.pageSize ?? 50,
  };
}

export const usageApi = {
  getDashboard: async (params: { period?: UsagePeriod; limit?: number } = {}): Promise<UsageDashboard> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/usage/dashboard', {
      params: {
        period: params.period ?? 'month',
        limit: params.limit ?? 50,
      },
    });

    return toCamelCase<UsageDashboard>(response.data);
  },
  getSearchDashboard: async (params: SearchUsageFilters = {}): Promise<SearchUsageDashboard> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/usage/search/dashboard', {
      params: searchParams(params),
    });
    return toCamelCase<SearchUsageDashboard>(response.data);
  },
  getSearchFaults: async (): Promise<SearchFaultStatus> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/usage/search/faults');
    return toCamelCase<SearchFaultStatus>(response.data);
  },
  getSearchCall: async (callId: number): Promise<SearchUsageCallDetail> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/usage/search/calls/${callId}`);
    return toCamelCase<SearchUsageCallDetail>(response.data);
  },
  downloadSearchCsv: async (params: SearchUsageFilters = {}): Promise<Blob> => {
    const response = await apiClient.get('/api/v1/usage/search/export.csv', {
      params: searchParams(params),
      responseType: 'blob',
    });
    return response.data as Blob;
  },
  downloadSearchCallJson: async (callId: number): Promise<Blob> => {
    const response = await apiClient.get(`/api/v1/usage/search/calls/${callId}/export.json`, {
      responseType: 'blob',
    });
    return response.data as Blob;
  },
};
