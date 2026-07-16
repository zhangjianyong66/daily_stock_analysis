import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Copy, Download, Eye, RefreshCw, Search } from 'lucide-react';
import {
  usageApi,
  type SearchUsageCall,
  type SearchUsageCallDetail,
  type SearchUsageDashboard,
  type SearchUsageFilters,
  type SearchUsagePeriod,
} from '../../api/usage';
import { useAuth } from '../../contexts/AuthContext';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Card, Drawer, InlineAlert, StatCard } from '../common';
import { cn } from '../../utils/cn';
import { getSearchErrorLabel, SEARCH_ERROR_CATEGORIES } from './searchUsageLabels';

const PERIODS: SearchUsagePeriod[] = ['today', '7d', 'month', 'all', 'custom'];

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function SearchUsagePanel() {
  const { language } = useUiLanguage();
  const { authEnabled, loggedIn } = useAuth();
  const zh = language !== 'en';
  const canSensitive = authEnabled && loggedIn;
  const [period, setPeriod] = useState<SearchUsagePeriod>('month');
  const [fromTime, setFromTime] = useState('');
  const [toTime, setToTime] = useState('');
  const [provider, setProvider] = useState('');
  const [source, setSource] = useState('');
  const [success, setSuccess] = useState('');
  const [errorCategory, setErrorCategory] = useState('');
  const [keyFingerprint, setKeyFingerprint] = useState('');
  const [page, setPage] = useState(1);
  const [dashboard, setDashboard] = useState<SearchUsageDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<SearchUsageCallDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const requestSeq = useRef(0);

  const filters = useMemo<SearchUsageFilters>(() => ({
    period,
    fromTime: period === 'custom' ? fromTime : undefined,
    toTime: period === 'custom' ? toTime : undefined,
    provider: provider || undefined,
    source: source || undefined,
    success: success === '' ? undefined : success === 'true',
    errorCategory: errorCategory || undefined,
    keyFingerprint: keyFingerprint || undefined,
    page,
    pageSize: 50,
  }), [errorCategory, fromTime, keyFingerprint, page, period, provider, source, success, toTime]);

  const load = useCallback(async () => {
    if (period === 'custom' && (!fromTime || !toTime)) {
      setLoading(false);
      return;
    }
    const seq = ++requestSeq.current;
    setLoading(true);
    setError('');
    try {
      const data = await usageApi.getSearchDashboard(filters);
      if (seq === requestSeq.current) setDashboard(data);
    } catch (err) {
      if (seq === requestSeq.current) setError(err instanceof Error ? err.message : (zh ? '搜索调用数据加载失败' : 'Failed to load search usage'));
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [filters, fromTime, period, toTime, zh]);

  useEffect(() => {
    void load();
    return () => { requestSeq.current += 1; };
  }, [load]);

  const providers = dashboard?.byProvider.map((item) => item.value) ?? [];
  const sources = dashboard?.bySource.map((item) => item.value) ?? [];
  const keys = dashboard?.byKey.map((item) => item.value) ?? [];
  const totalPages = Math.max(1, Math.ceil((dashboard?.calls.total ?? 0) / 50));

  const openDetail = async (call: SearchUsageCall) => {
    if (!canSensitive) return;
    setDetailLoading(true);
    setError('');
    try {
      setDetail(await usageApi.getSearchCall(call.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : (zh ? '详情加载失败' : 'Failed to load details'));
    } finally {
      setDetailLoading(false);
    }
  };

  const exportCsv = async () => downloadBlob(await usageApi.downloadSearchCsv(filters), 'search-usage.csv');
  const exportJson = async (callId: number) => downloadBlob(await usageApi.downloadSearchCallJson(callId), `search-call-${callId}.json`);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex flex-wrap rounded-xl border border-border/70 bg-card/70 p-1">
          {PERIODS.map((item) => (
            <button key={item} type="button" onClick={() => { setPage(1); setPeriod(item); }} className={cn('rounded-lg px-3 py-1.5 text-sm', period === item ? 'bg-cyan text-background' : 'text-secondary-text hover:bg-hover')}>
              {({ today: zh ? '今日' : 'Today', '7d': zh ? '最近 7 天' : 'Last 7 days', month: zh ? '本月' : 'This month', all: zh ? '全部' : 'All', custom: zh ? '自定义' : 'Custom' })[item]}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />{zh ? '刷新' : 'Refresh'}
          </button>
          <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void exportCsv()} disabled={!canSensitive} title={!canSensitive ? (zh ? '需启用管理员认证并登录' : 'Enable admin auth and sign in') : undefined}>
            <Download className="h-4 w-4" />CSV
          </button>
        </div>
      </div>

      {period === 'custom' ? <div className="grid gap-3 sm:grid-cols-2"><input type="datetime-local" className="input" value={fromTime} onChange={(e) => { setPage(1); setFromTime(e.target.value); }} /><input type="datetime-local" className="input" value={toTime} onChange={(e) => { setPage(1); setToTime(e.target.value); }} /></div> : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <select className="input" value={provider} onChange={(e) => { setPage(1); setProvider(e.target.value); }}><option value="">{zh ? '全部供应商' : 'All providers'}</option>{providers.map((value) => <option key={value}>{value}</option>)}</select>
        <select className="input" value={source} onChange={(e) => { setPage(1); setSource(e.target.value); }}><option value="">{zh ? '全部来源' : 'All sources'}</option>{sources.map((value) => <option key={value}>{value}</option>)}</select>
        <select className="input" value={success} onChange={(e) => { setPage(1); setSuccess(e.target.value); }}><option value="">{zh ? '全部状态' : 'All statuses'}</option><option value="true">{zh ? '成功' : 'Success'}</option><option value="false">{zh ? '失败' : 'Failed'}</option></select>
        <select className="input" value={errorCategory} onChange={(e) => { setPage(1); setErrorCategory(e.target.value); }}><option value="">{zh ? '全部错误' : 'All errors'}</option>{SEARCH_ERROR_CATEGORIES.map((value) => <option key={value} value={value}>{getSearchErrorLabel(value, language)}</option>)}</select>
        <select className="input" value={keyFingerprint} onChange={(e) => { setPage(1); setKeyFingerprint(e.target.value); }}><option value="">{zh ? '全部 Key' : 'All keys'}</option>{keys.map((value) => <option key={value} value={value}>{value.slice(0, 12)}</option>)}</select>
      </div>

      {error ? <InlineAlert variant="danger" title={zh ? '加载失败' : 'Load failed'} message={error} /> : null}
      {!canSensitive ? <InlineAlert variant="warning" title={zh ? '敏感操作受限' : 'Sensitive actions restricted'} message={zh ? '完整请求/响应详情、复制与导出仅在启用管理员认证且管理员已登录时可用。' : 'Full request/response details, copy, and exports require enabled admin authentication and an active admin session.'} /> : null}
      {dashboard && !dashboard.auditHealth.healthy ? <InlineAlert variant="danger" title={zh ? '审计链路存在缺口' : 'Audit gaps detected'} message={zh ? `已检测到 ${dashboard.auditHealth.processLostCount + dashboard.auditHealth.persistedLostCount} 条可能未落库的调用。` : `${dashboard.auditHealth.processLostCount + dashboard.auditHealth.persistedLostCount} calls may be missing from the audit ledger.`} /> : null}
      {dashboard?.faults.activeFaults.length ? <InlineAlert variant="danger" title={zh ? '搜索供应商持续故障' : 'Search provider fault'} message={dashboard.faults.activeFaults.map((fault) => `${fault.provider} · ${fault.keyFingerprint.slice(0, 8)} · ${getSearchErrorLabel(fault.errorCategory, language)}`).join('；')} /> : null}

      {dashboard ? <>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard label={zh ? '真实外部请求' : 'Physical requests'} value={dashboard.summary.physicalRequests} hint={dashboard.auditStartedAt ? `${zh ? '审计始于' : 'Auditing since'} ${new Date(dashboard.auditStartedAt).toLocaleString()}` : (zh ? '暂无正式审计记录' : 'No audited calls yet')} icon={<Search className="h-5 w-5" />} tone="primary" />
          <StatCard label={zh ? '业务搜索任务' : 'Business searches'} value={dashboard.summary.businessSearches} hint={zh ? '按业务搜索 ID 去重' : 'Unique business search IDs'} />
          <StatCard label={zh ? '成功请求' : 'Successful'} value={dashboard.summary.successCount} hint={`${(dashboard.summary.successRate * 100).toFixed(1)}%`} />
          <StatCard label={zh ? '失败请求' : 'Failed'} value={dashboard.summary.failureCount} hint={zh ? '含重试与 fallback' : 'Includes retries and fallbacks'} icon={<AlertTriangle className="h-5 w-5" />} />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {([
            [zh ? '供应商分布' : 'Provider distribution', dashboard.byProvider],
            [zh ? 'Key 指纹分布' : 'Key distribution', dashboard.byKey],
            [zh ? '调用来源分布' : 'Source distribution', dashboard.bySource],
          ] as const).map(([title, items]) => <Card key={title} title={title}><div className="space-y-2">{items.length ? items.map((item) => <div key={item.value} className="flex items-center justify-between gap-3 text-sm"><span className="truncate text-secondary-text" title={item.value}>{title.includes('Key') ? item.value.slice(0, 12) : item.value}</span><span className="font-medium text-foreground">{item.count}</span></div>) : <p className="text-sm text-secondary-text">{zh ? '暂无数据' : 'No data'}</p>}</div></Card>)}
        </div>

        <Card title={zh ? '最近搜索调用' : 'Recent search calls'} subtitle={zh ? '每次真实外部 HTTP 请求独立一行' : 'One row per real outbound HTTP request'}>
          <div className="overflow-x-auto">
            <table className="min-w-[1050px] w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-secondary-text"><tr><th className="py-3">{zh ? '时间' : 'Time'}</th><th>{zh ? '供应商 / Key' : 'Provider / Key'}</th><th>{zh ? '来源 / 维度' : 'Source / Dimension'}</th><th>{zh ? '尝试' : 'Attempt'}</th><th>{zh ? '状态' : 'Status'}</th><th>{zh ? '耗时' : 'Latency'}</th><th>{zh ? '结果' : 'Results'}</th><th>{zh ? '操作' : 'Actions'}</th></tr></thead>
              <tbody className="divide-y divide-border/60">{dashboard.calls.items.map((call) => <tr key={call.id} className="hover:bg-hover/60"><td className="py-3 pr-4 whitespace-nowrap text-secondary-text">{new Date(call.requestedAt).toLocaleString()}</td><td className="pr-4"><div className="font-medium">{call.provider}</div><div className="text-xs text-secondary-text">{call.keyFingerprint.slice(0, 12)}</div></td><td className="pr-4"><div>{call.callSource}</div><div className="text-xs text-secondary-text">{call.dimension || call.operation}</div></td><td className="pr-4">{call.providerAttempt}.{call.physicalAttempt}</td><td className="pr-4"><span className={call.success ? 'text-success' : 'text-danger'}>{call.success ? (zh ? '成功' : 'Success') : getSearchErrorLabel(call.errorCategory, language)}</span>{call.httpStatus ? <div className="text-xs text-secondary-text">HTTP {call.httpStatus}</div> : null}</td><td className="pr-4">{call.durationMs} ms</td><td className="pr-4">{call.resultCount ?? '-'}</td><td><button type="button" className="btn-ghost inline-flex items-center gap-1" disabled={!canSensitive || detailLoading} onClick={() => void openDetail(call)}><Eye className="h-4 w-4" />{zh ? '详情' : 'Details'}</button></td></tr>)}</tbody>
            </table>
          </div>
          {!dashboard.calls.items.length ? <p className="py-8 text-center text-secondary-text">{zh ? '暂无搜索调用记录' : 'No search calls'}</p> : null}
          <div className="mt-4 flex items-center justify-between"><span className="text-sm text-secondary-text">{dashboard.calls.total} {zh ? '条' : 'records'}</span><div className="flex items-center gap-2"><button className="btn-secondary" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>{zh ? '上一页' : 'Previous'}</button><span>{page}/{totalPages}</span><button className="btn-secondary" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>{zh ? '下一页' : 'Next'}</button></div></div>
        </Card>
      </> : null}

      <Drawer isOpen={Boolean(detail)} onClose={() => setDetail(null)} title={zh ? '搜索调用详情' : 'Search call details'} width="max-w-4xl">
        {detail ? <div className="space-y-5"><div className="flex flex-wrap gap-2"><button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void navigator.clipboard.writeText(pretty(detail.requestSnapshot))}><Copy className="h-4 w-4" />{zh ? '复制请求' : 'Copy request'}</button><button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void navigator.clipboard.writeText(pretty(detail.responseSnapshot))}><Copy className="h-4 w-4" />{zh ? '复制响应' : 'Copy response'}</button><button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void exportJson(detail.id)}><Download className="h-4 w-4" />JSON</button></div>{detail.requestTruncated ? <InlineAlert variant="warning" message={`Request truncated · ${detail.requestSizeBytes} bytes · SHA-256 ${detail.requestSha256}`} /> : null}<section><h3 className="font-semibold">Request</h3><pre className="mt-2 max-h-[34vh] overflow-auto rounded-xl bg-background p-4 text-xs">{pretty(detail.requestSnapshot)}</pre></section>{detail.responseTruncated ? <InlineAlert variant="warning" message={`Response truncated · ${detail.responseSizeBytes} bytes · SHA-256 ${detail.responseSha256}`} /> : null}<section><h3 className="font-semibold">Response</h3><pre className="mt-2 max-h-[34vh] overflow-auto rounded-xl bg-background p-4 text-xs">{pretty(detail.responseSnapshot)}</pre></section></div> : null}
      </Drawer>
    </div>
  );
}
