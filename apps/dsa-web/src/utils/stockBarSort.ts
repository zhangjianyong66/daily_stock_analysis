import type { UiLanguage } from '../i18n/uiText';
import type { StockBarItem } from '../types/analysis';

export const STOCK_BAR_SORT_STORAGE_KEY = 'dsa.stockBarSort.v1';

export const STOCK_BAR_SORT_OPTIONS = [
  'recent',
  'highest-sentiment',
  'lowest-sentiment',
  'name-code',
] as const;

export type StockBarSortOption = typeof STOCK_BAR_SORT_OPTIONS[number];

export const DEFAULT_STOCK_BAR_SORT: StockBarSortOption = 'recent';

export function normalizeStockBarSort(value?: string | null): StockBarSortOption | null {
  return STOCK_BAR_SORT_OPTIONS.find((option) => option === value) ?? null;
}

export function getStockBarSortStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function resolveInitialStockBarSort(storage = getStockBarSortStorage()): StockBarSortOption {
  if (!storage) {
    return DEFAULT_STOCK_BAR_SORT;
  }

  try {
    return normalizeStockBarSort(storage.getItem(STOCK_BAR_SORT_STORAGE_KEY)) ?? DEFAULT_STOCK_BAR_SORT;
  } catch {
    return DEFAULT_STOCK_BAR_SORT;
  }
}

export function persistStockBarSort(storage: Storage | null, option: StockBarSortOption): void {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(STOCK_BAR_SORT_STORAGE_KEY, option);
  } catch {
    // Keep the in-memory selection when browser storage is unavailable.
  }
}

function parseAnalysisTime(value?: string): number | null {
  if (!value) {
    return null;
  }

  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function compareOptionalNumbers(
  left: number | null,
  right: number | null,
  direction: 'asc' | 'desc',
): number {
  if (left === null || right === null) {
    if (left === right) return 0;
    return left === null ? 1 : -1;
  }
  if (left === right) return 0;
  return direction === 'asc' ? left - right : right - left;
}

function compareText(collator: Intl.Collator, left: string, right: string): number {
  const localized = collator.compare(left, right);
  if (localized !== 0) {
    return localized;
  }
  if (left === right) {
    return 0;
  }
  return left < right ? -1 : 1;
}

function compareCode(collator: Intl.Collator, left: StockBarItem, right: StockBarItem): number {
  const codeOrder = compareText(collator, left.stockCode, right.stockCode);
  return codeOrder !== 0 ? codeOrder : left.id - right.id;
}

function compareRecentThenCode(
  collator: Intl.Collator,
  left: StockBarItem,
  right: StockBarItem,
): number {
  const timeOrder = compareOptionalNumbers(
    parseAnalysisTime(left.lastAnalysisTime),
    parseAnalysisTime(right.lastAnalysisTime),
    'desc',
  );
  return timeOrder !== 0 ? timeOrder : compareCode(collator, left, right);
}

export function sortStockBarItems(
  items: StockBarItem[],
  option: StockBarSortOption,
  language: UiLanguage,
): StockBarItem[] {
  const collator = new Intl.Collator(language === 'en' ? 'en' : 'zh-CN', {
    numeric: true,
    sensitivity: 'base',
  });

  return [...items].sort((left, right) => {
    let primaryOrder = 0;

    switch (option) {
      case 'recent':
        return compareRecentThenCode(collator, left, right);
      case 'highest-sentiment':
        primaryOrder = compareOptionalNumbers(
          finiteNumber(left.sentimentScore),
          finiteNumber(right.sentimentScore),
          'desc',
        );
        break;
      case 'lowest-sentiment':
        primaryOrder = compareOptionalNumbers(
          finiteNumber(left.sentimentScore),
          finiteNumber(right.sentimentScore),
          'asc',
        );
        break;
      case 'name-code': {
        const leftName = left.stockName?.trim() || left.stockCode;
        const rightName = right.stockName?.trim() || right.stockCode;
        primaryOrder = compareText(collator, leftName, rightName);
        return primaryOrder !== 0 ? primaryOrder : compareCode(collator, left, right);
      }
    }

    return primaryOrder !== 0 ? primaryOrder : compareRecentThenCode(collator, left, right);
  });
}
