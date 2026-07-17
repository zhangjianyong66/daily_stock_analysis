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

const SOURCE_LABELS: Record<string, string> = {
  analysis: '分析流程',
  agent: 'Agent 工具',
  market_review: '大盘复盘',
  alphasift: 'AlphaSift',
  availability_smoke: '可用性检测',
  market_data_fallback: '行情降级搜索',
  direct: '直接调用',
};

const DIMENSION_LABELS: Record<string, string> = {
  latest_news: '最新消息',
  market_analysis: '机构分析',
  risk_check: '风险排查',
  announcements: '公司公告',
  earnings: '业绩预期',
  industry: '行业分析',
  fresh_events: '近期事件',
  analysis: '综合分析',
  events: '事件搜索',
};

const OPERATION_LABELS: Record<string, string> = {
  search_stock_news: '股票新闻搜索',
  search_comprehensive_intel: '综合情报搜索',
  search_stock_events: '股票事件搜索',
  search_stock_price_fallback: '股价降级搜索',
  provider_search: '供应商搜索',
  search_stock_news_cache: '股票新闻缓存',
  search_stock_news_cache_retry: '股票新闻缓存重试',
  search_stock_news_cache_wait: '等待股票新闻缓存',
  search_comprehensive_intel_cache: '综合情报缓存',
};

export function getSearchErrorLabel(category: string | null | undefined, language: UiLanguage): string {
  if (!category) return language === 'en' ? 'Failed' : '失败';
  const labels = LABELS[category];
  return labels ? labels[language === 'en' ? 'en' : 'zh'] : category;
}

export function getSearchSourceLabel(source: string, language: UiLanguage): string {
  return language === 'en' ? source : (SOURCE_LABELS[source] ?? source);
}

export function getSearchDimensionLabel(dimension: string, language: UiLanguage): string {
  if (language === 'en') return dimension;
  const priceAttempt = /^price_attempt_(\d+)$/.exec(dimension);
  if (priceAttempt) return `股价搜索第 ${priceAttempt[1]} 次尝试`;
  return DIMENSION_LABELS[dimension] ?? dimension;
}

export function getSearchOperationLabel(operation: string, language: UiLanguage): string {
  return language === 'en' ? operation : (OPERATION_LABELS[operation] ?? operation);
}
