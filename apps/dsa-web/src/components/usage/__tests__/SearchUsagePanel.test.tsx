import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SearchUsagePanel } from '../SearchUsagePanel';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../../../api/index', () => ({ default: { get } }));
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ authEnabled: true, loggedIn: true }),
}));

const dashboard = {
  audit_started_at: '2026-07-16T10:00:00+08:00',
  summary: { physical_requests: 2, business_searches: 1, success_count: 1, failure_count: 1, success_rate: 0.5 },
  by_provider: [{ value: 'Anspire', count: 2 }],
  by_key: [{ value: 'abcdef0123456789', count: 2 }],
  by_source: [{ value: 'analysis', count: 2 }],
  calls: {
    total: 1, page: 1, page_size: 50,
    items: [{
      id: 7, business_search_id: 'business', logical_request_id: 'logical', provider: 'Anspire', endpoint: 'https://plugin.anspire.cn/search', http_method: 'GET', call_source: 'analysis', operation: 'search_comprehensive_intel', dimension: 'earnings', provider_attempt: 1, physical_attempt: 1, key_fingerprint: 'abcdef0123456789', success: false, http_status: 401, duration_ms: 120, result_count: 0, error_category: 'quota_exhausted', request_truncated: false, request_size_bytes: 120, request_sha256: 'a'.repeat(64), response_truncated: false, response_size_bytes: 140, response_sha256: 'b'.repeat(64), requested_at: '2026-07-16T10:00:00+08:00', completed_at: '2026-07-16T10:00:00+08:00',
    }],
  },
  faults: { active_faults: [], providers: [], audit_health: { healthy: true, process_lost_count: 0, persisted_lost_count: 0 } },
  audit_health: { healthy: true, process_lost_count: 0, persisted_lost_count: 0 },
};

describe('SearchUsagePanel', () => {
  beforeEach(() => {
    window.localStorage.setItem('dsa.uiLanguage', 'zh');
    get.mockReset();
    get.mockResolvedValue({ data: dashboard });
  });

  it('shows physical call totals, failure category, and requests admin detail on demand', async () => {
    get.mockResolvedValueOnce({ data: dashboard }).mockResolvedValueOnce({ data: {
      ...dashboard.calls.items[0], request_snapshot: { query_params: { query: '业绩预期' } }, response_snapshot: { body: { message: '余额不足' } },
    } });
    render(<UiLanguageProvider><SearchUsagePanel /></UiLanguageProvider>);
    expect(await screen.findByText('真实外部请求')).toBeInTheDocument();
    expect(screen.getAllByText('分析流程')).toHaveLength(3);
    expect(screen.getByText('业绩预期')).toBeInTheDocument();
    expect(screen.getAllByText('余额不足/额度耗尽')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getAllByText(/业绩预期/)).toHaveLength(2);
    expect(get).toHaveBeenLastCalledWith('/api/v1/usage/search/calls/7');
  });

  it('keeps the source code as the server-side filter value', async () => {
    render(<UiLanguageProvider><SearchUsagePanel /></UiLanguageProvider>);
    await screen.findByText('真实外部请求');

    fireEvent.change(screen.getByDisplayValue('全部来源'), { target: { value: 'analysis' } });

    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/api/v1/usage/search/dashboard', {
      params: expect.objectContaining({ source: 'analysis' }),
    }));
  });

  it('uses the translated operation when a call has no dimension', async () => {
    get.mockResolvedValueOnce({ data: {
      ...dashboard,
      by_source: [{ value: 'direct', count: 1 }],
      calls: {
        ...dashboard.calls,
        items: [{
          ...dashboard.calls.items[0],
          call_source: 'direct',
          operation: 'provider_search',
          dimension: null,
        }],
      },
    } });

    render(<UiLanguageProvider><SearchUsagePanel /></UiLanguageProvider>);

    expect(await screen.findAllByText('直接调用')).toHaveLength(3);
    expect(screen.getByText('供应商搜索')).toBeInTheDocument();
  });
});
