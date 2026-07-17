import { describe, expect, it } from 'vitest';
import {
  getSearchDimensionLabel,
  getSearchOperationLabel,
  getSearchSourceLabel,
} from '../searchUsageLabels';

describe('search usage labels', () => {
  it('translates known source, dimension, and fallback operation codes in Chinese', () => {
    expect(getSearchSourceLabel('market_review', 'zh')).toBe('大盘复盘');
    expect(getSearchDimensionLabel('fresh_events', 'zh')).toBe('近期事件');
    expect(getSearchOperationLabel('search_stock_news', 'zh')).toBe('股票新闻搜索');
  });

  it('formats price attempt dimensions without losing the attempt number', () => {
    expect(getSearchDimensionLabel('price_attempt_3', 'zh')).toBe('股价搜索第 3 次尝试');
  });

  it('keeps unknown codes and all English values unchanged', () => {
    expect(getSearchSourceLabel('new_source', 'zh')).toBe('new_source');
    expect(getSearchDimensionLabel('new_dimension', 'zh')).toBe('new_dimension');
    expect(getSearchOperationLabel('new_operation', 'zh')).toBe('new_operation');
    expect(getSearchSourceLabel('analysis', 'en')).toBe('analysis');
    expect(getSearchDimensionLabel('earnings', 'en')).toBe('earnings');
    expect(getSearchOperationLabel('search_stock_news', 'en')).toBe('search_stock_news');
  });
});
