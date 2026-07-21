import { describe, expect, it } from 'vitest';
import type { StockBarItem } from '../../types/analysis';
import {
  isStockBarItemPinned,
  normalizeStockBarPinCode,
  persistStockBarPins,
  prioritizePinnedStockBarItems,
  resolveInitialStockBarPins,
  STOCK_BAR_PINS_STORAGE_KEY,
} from '../stockBarPins';

function createStorage(initialValue?: string): Storage {
  const values = new Map<string, string>();
  if (initialValue !== undefined) {
    values.set(STOCK_BAR_PINS_STORAGE_KEY, initialValue);
  }

  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  } as unknown as Storage;
}

describe('stockBarPins', () => {
  it('normalizes stock codes while excluding empty and MARKET values', () => {
    expect(normalizeStockBarPinCode('  aapl ')).toBe('AAPL');
    expect(normalizeStockBarPinCode('510300.sh')).toBe('510300.SH');
    expect(normalizeStockBarPinCode('')).toBeNull();
    expect(normalizeStockBarPinCode(' market ')).toBeNull();
    expect(normalizeStockBarPinCode(510300)).toBeNull();
  });

  it('restores unique valid codes and ignores invalid persisted entries', () => {
    const storage = createStorage(JSON.stringify([
      ' aapl ',
      'AAPL',
      '510300.sh',
      'MARKET',
      '',
      null,
      123,
    ]));

    expect([...resolveInitialStockBarPins(storage)]).toEqual(['AAPL', '510300.SH']);
  });

  it.each([
    ['invalid JSON', '{'],
    ['a non-array value', JSON.stringify({ code: 'AAPL' })],
  ])('falls back to an empty set for %s', (_label, storedValue) => {
    expect(resolveInitialStockBarPins(createStorage(storedValue))).toEqual(new Set());
  });

  it('persists normalized codes in deterministic order and tolerates storage failures', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    } as unknown as Storage;

    persistStockBarPins(storage, [' aapl ', '510300.sh', 'AAPL', 'MARKET']);
    expect(values.get(STOCK_BAR_PINS_STORAGE_KEY)).toBe('["510300.SH","AAPL"]');

    const throwingStorage = {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
    } as unknown as Storage;
    expect(resolveInitialStockBarPins(throwingStorage)).toEqual(new Set());
    expect(() => persistStockBarPins(throwingStorage, ['AAPL'])).not.toThrow();
    expect(() => persistStockBarPins(null, ['AAPL'])).not.toThrow();
  });

  it('moves pinned items first without changing either group order or mutating input', () => {
    const items: StockBarItem[] = [
      { id: 1, stockCode: 'AAPL', analysisCount: 1 },
      { id: 2, stockCode: 'MARKET', analysisCount: 1 },
      { id: 3, stockCode: '510300.SH', analysisCount: 1 },
      { id: 4, stockCode: '600519', analysisCount: 1 },
    ];

    const prioritized = prioritizePinnedStockBarItems(
      items,
      new Set(['600519', '510300.SH', 'MARKET']),
    );

    expect(prioritized.map((item) => item.stockCode)).toEqual([
      '510300.SH',
      '600519',
      'AAPL',
      'MARKET',
    ]);
    expect(items.map((item) => item.stockCode)).toEqual([
      'AAPL',
      'MARKET',
      '510300.SH',
      '600519',
    ]);
    expect(isStockBarItemPinned(new Set(['AAPL']), ' aapl ')).toBe(true);
    expect(isStockBarItemPinned(new Set(['MARKET']), 'MARKET')).toBe(false);
  });
});
