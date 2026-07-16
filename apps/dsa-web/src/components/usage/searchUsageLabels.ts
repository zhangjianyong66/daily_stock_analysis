import type { UiLanguage } from '../../i18n/uiText';

export const SEARCH_ERROR_CATEGORIES = [
  'quota_exhausted',
  'auth_invalid',
  'permission_denied',
  'account_disabled',
  'rate_limited',
  'timeout',
  'connection_error',
  'provider_5xx',
  'invalid_response',
  'other',
] as const;

const LABELS: Record<string, { zh: string; en: string }> = {
  quota_exhausted: { zh: '余额不足/额度耗尽', en: 'Balance/quota exhausted' },
  auth_invalid: { zh: 'API Key 无效', en: 'Invalid API key' },
  permission_denied: { zh: '权限不足', en: 'Permission denied' },
  account_disabled: { zh: '账户停用', en: 'Account disabled' },
  rate_limited: { zh: '请求限流', en: 'Rate limited' },
  timeout: { zh: '请求超时', en: 'Timeout' },
  connection_error: { zh: '连接失败', en: 'Connection error' },
  provider_5xx: { zh: '供应商服务异常', en: 'Provider 5xx' },
  invalid_response: { zh: '响应格式异常', en: 'Invalid response' },
  other: { zh: '其他错误', en: 'Other error' },
};

export function getSearchErrorLabel(category: string | null | undefined, language: UiLanguage): string {
  if (!category) return language === 'en' ? 'Failed' : '失败';
  const labels = LABELS[category];
  return labels ? labels[language === 'en' ? 'en' : 'zh'] : category;
}
