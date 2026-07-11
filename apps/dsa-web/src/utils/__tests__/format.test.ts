import { afterEach, describe, expect, it, vi } from 'vitest';
import { getRecentStartDate, getTodayInShanghai } from '../format';

const originalDateTimeFormat = Intl.DateTimeFormat;

describe('Shanghai date helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Intl.DateTimeFormat = originalDateTimeFormat;
  });

  it('returns ISO date strings even when Intl.format uses slash dates', () => {
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(function MockDateTimeFormat() {
      return {
        format: () => '7/10/2026',
        formatToParts: () => [
        { type: 'month', value: '07' },
        { type: 'literal', value: '/' },
        { type: 'day', value: '10' },
        { type: 'literal', value: '/' },
        { type: 'year', value: '2026' },
      ],
      } as Intl.DateTimeFormat;
    } as unknown as typeof Intl.DateTimeFormat);

    expect(getTodayInShanghai()).toBe('2026-07-10');
    expect(getRecentStartDate(0)).toBe('2026-07-10');
  });
});
