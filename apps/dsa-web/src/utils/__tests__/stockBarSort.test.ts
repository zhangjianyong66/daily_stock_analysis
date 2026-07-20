import { describe, expect, it } from 'vitest';
import type { StockBarItem } from '../../types/analysis';
import {
  DEFAULT_STOCK_BAR_SORT,
  normalizeStockBarSort,
  persistStockBarSort,
  resolveInitialStockBarSort,
  sortStockBarItems,
  STOCK_BAR_SORT_STORAGE_KEY,
} from '../stockBarSort';

const items: StockBarItem[] = [
  {
    id: 1,
    stockCode: '600519',
    stockName: '贵州茅台',
    analysisCount: 2,
    sentimentScore: 68,
    lastAnalysisTime: '2026-07-10T08:00:00Z',
  },
  {
    id: 2,
    stockCode: '000001',
    stockName: '平安银行',
    analysisCount: 3,
    sentimentScore: 0,
    lastAnalysisTime: '2026-07-11T08:00:00Z',
  },
  {
    id: 3,
    stockCode: 'AAPL',
    stockName: 'Apple',
    analysisCount: 0,
    sentimentScore: 72,
    lastAnalysisTime: '2026-07-12T08:00:00Z',
  },
];

describe('stockBarSort', () => {
  it('sorts every supported option without mutating the source list', () => {
    const sourceOrder = items.map((item) => item.stockCode);

    expect(sortStockBarItems(items, 'recent', 'zh').map((item) => item.stockCode)).toEqual([
      'AAPL', '000001', '600519',
    ]);
    expect(sortStockBarItems(items, 'highest-sentiment', 'zh').map((item) => item.stockCode)).toEqual([
      'AAPL', '600519', '000001',
    ]);
    expect(sortStockBarItems(items, 'lowest-sentiment', 'zh').map((item) => item.stockCode)).toEqual([
      '000001', '600519', 'AAPL',
    ]);
    expect(sortStockBarItems(items, 'name-code', 'zh').map((item) => item.stockCode)).toEqual([
      '600519', '000001', 'AAPL',
    ]);
    expect(items.map((item) => item.stockCode)).toEqual(sourceOrder);
  });

  it('places missing values last, treats zero as valid, and uses recent time then code for ties', () => {
    const edgeItems: StockBarItem[] = [
      { id: 1, stockCode: '10', analysisCount: Number.NaN, sentimentScore: Number.NaN, lastAnalysisTime: 'invalid' },
      { id: 2, stockCode: '2', analysisCount: 0, sentimentScore: 0, lastAnalysisTime: '2026-07-10T08:00:00Z' },
      { id: 3, stockCode: 'TIE-OLD', analysisCount: 5, sentimentScore: 50, lastAnalysisTime: '2026-07-11T08:00:00Z' },
      { id: 4, stockCode: 'TIE-NEW', analysisCount: 5, sentimentScore: 50, lastAnalysisTime: '2026-07-12T08:00:00Z' },
      { id: 5, stockCode: 'MISSING', analysisCount: 1 },
    ];

    expect(sortStockBarItems(edgeItems, 'recent', 'en').map((item) => item.stockCode)).toEqual([
      'TIE-NEW', 'TIE-OLD', '2', '10', 'MISSING',
    ]);
    expect(sortStockBarItems(edgeItems, 'highest-sentiment', 'en').map((item) => item.stockCode)).toEqual([
      'TIE-NEW', 'TIE-OLD', '2', '10', 'MISSING',
    ]);
    expect(sortStockBarItems(edgeItems, 'lowest-sentiment', 'en').map((item) => item.stockCode)).toEqual([
      '2', 'TIE-NEW', 'TIE-OLD', '10', 'MISSING',
    ]);
    expect(sortStockBarItems(edgeItems.slice(0, 2), 'name-code', 'en').map((item) => item.stockCode)).toEqual([
      '2', '10',
    ]);
  });

  it('normalizes persisted values and safely falls back when storage fails', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    } as unknown as Storage;

    persistStockBarSort(storage, 'lowest-sentiment');
    expect(values.get(STOCK_BAR_SORT_STORAGE_KEY)).toBe('lowest-sentiment');
    expect(resolveInitialStockBarSort(storage)).toBe('lowest-sentiment');

    values.set(STOCK_BAR_SORT_STORAGE_KEY, 'oldest');
    expect(resolveInitialStockBarSort(storage)).toBe(DEFAULT_STOCK_BAR_SORT);
    values.set(STOCK_BAR_SORT_STORAGE_KEY, 'most-analyzed');
    expect(resolveInitialStockBarSort(storage)).toBe(DEFAULT_STOCK_BAR_SORT);

    values.set(STOCK_BAR_SORT_STORAGE_KEY, 'unsupported');
    expect(resolveInitialStockBarSort(storage)).toBe(DEFAULT_STOCK_BAR_SORT);
    expect(normalizeStockBarSort('unsupported')).toBeNull();

    const throwingStorage = {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
    } as unknown as Storage;
    expect(resolveInitialStockBarSort(throwingStorage)).toBe(DEFAULT_STOCK_BAR_SORT);
    expect(() => persistStockBarSort(throwingStorage, 'lowest-sentiment')).not.toThrow();
  });
});
