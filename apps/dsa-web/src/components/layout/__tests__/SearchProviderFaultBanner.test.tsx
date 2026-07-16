import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SearchProviderFaultBanner } from '../SearchProviderFaultBanner';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../../../api/index', () => ({ default: { get } }));

describe('SearchProviderFaultBanner', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.setItem('dsa.uiLanguage', 'zh');
    get.mockReset();
    get.mockResolvedValue({ data: {
      active_faults: [{ id: 1, provider: 'Anspire', key_fingerprint: 'abcdef012345', error_category: 'quota_exhausted', active: true, severity: 'warning', first_seen_at: '2026-07-16T10:00:00+08:00', last_seen_at: '2026-07-16T10:00:00+08:00', consecutive_count: 1 }],
      providers: [{ provider: 'Anspire', status: 'unavailable', configured_keys: 1, failed_keys: 1 }],
      audit_health: { healthy: true, process_lost_count: 0, persisted_lost_count: 0 },
    } });
  });

  it('shows an active provider fault and supports session-only dismissal', async () => {
    render(<MemoryRouter><UiLanguageProvider><SearchProviderFaultBanner /></UiLanguageProvider></MemoryRouter>);
    expect(await screen.findByText('搜索供应商持续故障')).toBeInTheDocument();
    expect(screen.getByText(/余额不足\/额度耗尽/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '本次关闭' }));
    expect(screen.queryByText('搜索供应商持续故障')).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem('dsa.searchFaultBanner.dismissed')).toContain('Anspire');
  });
});
