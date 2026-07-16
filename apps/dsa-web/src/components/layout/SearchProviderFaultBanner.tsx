import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { usageApi, type SearchFaultStatus } from '../../api/usage';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { InlineAlert } from '../common';
import { getSearchErrorLabel } from '../usage/searchUsageLabels';

const DISMISS_KEY = 'dsa.searchFaultBanner.dismissed';

export function SearchProviderFaultBanner() {
  const { language } = useUiLanguage();
  const [status, setStatus] = useState<SearchFaultStatus | null>(null);
  const [dismissedIdentity, setDismissedIdentity] = useState(() => window.sessionStorage.getItem(DISMISS_KEY) || '');

  const load = useCallback(async () => {
    try {
      setStatus(await usageApi.getSearchFaults());
    } catch {
      // The usage page exposes audit health errors; avoid replacing the whole shell with a polling error.
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 60_000);
    const onFocus = () => void load();
    window.addEventListener('focus', onFocus);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
    };
  }, [load]);

  const identity = useMemo(() => (status?.activeFaults ?? [])
    .map((fault) => `${fault.provider}:${fault.keyFingerprint}:${fault.errorCategory}:${fault.severity}`)
    .sort()
    .join('|'), [status]);

  if (!identity || identity === dismissedIdentity) return null;
  const zh = language !== 'en';
  const faults = status?.activeFaults ?? [];
  return (
    <InlineAlert
      variant="danger"
      className="mb-3"
      title={zh ? '搜索供应商持续故障' : 'Search provider fault'}
      message={faults.map((fault) => `${fault.provider} · ${fault.keyFingerprint.slice(0, 8)} · ${getSearchErrorLabel(fault.errorCategory, language)}`).join('；')}
      action={<div className="flex gap-2"><Link to="/usage" className="btn-secondary">{zh ? '查看用量' : 'View usage'}</Link><button type="button" className="btn-ghost" onClick={() => { window.sessionStorage.setItem(DISMISS_KEY, identity); setDismissedIdentity(identity); }}>{zh ? '本次关闭' : 'Dismiss'}</button></div>}
    />
  );
}
