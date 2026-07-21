import type { StockBarItem } from '../types/analysis';

export const STOCK_BAR_PINS_STORAGE_KEY = 'dsa.stockBarPins.v1';

export function normalizeStockBarPinCode(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const normalized = value.trim().toUpperCase();
  return normalized && normalized !== 'MARKET' ? normalized : null;
}

export function getStockBarPinsStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function resolveInitialStockBarPins(
  storage = getStockBarPinsStorage(),
): Set<string> {
  if (!storage) {
    return new Set();
  }

  try {
    const rawValue = storage.getItem(STOCK_BAR_PINS_STORAGE_KEY);
    if (!rawValue) {
      return new Set();
    }

    const parsedValue: unknown = JSON.parse(rawValue);
    if (!Array.isArray(parsedValue)) {
      return new Set();
    }

    return new Set(parsedValue.flatMap((value) => {
      const normalized = normalizeStockBarPinCode(value);
      return normalized ? [normalized] : [];
    }));
  } catch {
    return new Set();
  }
}

export function persistStockBarPins(
  storage: Storage | null,
  pinnedCodes: Iterable<string>,
): void {
  if (!storage) {
    return;
  }

  const normalizedCodes = [...new Set([...pinnedCodes].flatMap((value) => {
    const normalized = normalizeStockBarPinCode(value);
    return normalized ? [normalized] : [];
  }))].sort();

  try {
    storage.setItem(STOCK_BAR_PINS_STORAGE_KEY, JSON.stringify(normalizedCodes));
  } catch {
    // The in-memory selection remains usable when browser storage is unavailable.
  }
}

export function isStockBarItemPinned(
  pinnedCodes: ReadonlySet<string>,
  stockCode: string,
): boolean {
  const normalized = normalizeStockBarPinCode(stockCode);
  return normalized !== null && pinnedCodes.has(normalized);
}

export function prioritizePinnedStockBarItems(
  items: StockBarItem[],
  pinnedCodes: ReadonlySet<string>,
): StockBarItem[] {
  const pinnedItems: StockBarItem[] = [];
  const unpinnedItems: StockBarItem[] = [];

  items.forEach((item) => {
    if (isStockBarItemPinned(pinnedCodes, item.stockCode)) {
      pinnedItems.push(item);
    } else {
      unpinnedItems.push(item);
    }
  });

  return [...pinnedItems, ...unpinnedItems];
}
