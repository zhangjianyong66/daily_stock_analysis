import type React from 'react';
import { useState, useCallback, useRef, useEffect, useId, useMemo } from 'react';
import { ArrowUpDown, ChevronDown } from 'lucide-react';
import { Badge, Button, ConfirmDialog, ScrollArea } from '../common';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
import { StockBarItemComponent } from './StockBarItem';
import type { StockBarItem as StockBarItemType } from '../../types/analysis';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  getStockBarSortStorage,
  normalizeStockBarSort,
  persistStockBarSort,
  resolveInitialStockBarSort,
  sortStockBarItems,
  type StockBarSortOption,
} from '../../utils/stockBarSort';

interface StockBarProps {
  items: StockBarItemType[];
  isLoading: boolean;
  selectedStockCode?: string;
  selectedRecordId?: number;
  onItemClick: (recordId: number) => void;
  onDeleteStock?: (stockCode: string) => Promise<void> | void;
  isDeleting?: boolean;
  className?: string;
}

type PendingDelete = {
  mode: 'single' | 'batch';
  items: StockBarItemType[];
};

/**
 * 个股栏组件：以股票维度展示历史分析记录，每只股票只显示一条。
 * 大盘复盘可作为 MARKET 项参与展示，并与普通个股使用同一排序方案。
 */
export const StockBar: React.FC<StockBarProps> = ({
  items,
  isLoading,
  selectedStockCode,
  selectedRecordId,
  onItemClick,
  onDeleteStock,
  isDeleting = false,
  className = '',
}) => {
  const { language, t } = useUiLanguage();
  const isMarketReview = (code: string) => code === 'MARKET';
  const [filterText, setFilterText] = useState('');
  const [sortOption, setSortOption] = useState<StockBarSortOption>(resolveInitialStockBarSort);
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const selectAllId = useId();
  const sortId = useId();

  const normalizedFilter = filterText.trim().toLocaleLowerCase();
  const visibleItems = useMemo(() => {
    const filteredItems = !normalizedFilter ? items : items.filter((item) => {
      const stockCode = String(item.stockCode || '').toLocaleLowerCase();
      const stockName = String(item.stockName || '').toLocaleLowerCase();
      return stockCode.includes(normalizedFilter) || stockName.includes(normalizedFilter);
    });
    return sortStockBarItems(filteredItems, sortOption, language);
  }, [items, language, normalizedFilter, sortOption]);

  const sortOptions = useMemo(() => [
    { value: 'recent', label: t('stockBar.sortRecent') },
    { value: 'highest-sentiment', label: t('stockBar.sortHighestSentiment') },
    { value: 'lowest-sentiment', label: t('stockBar.sortLowestSentiment') },
    { value: 'name-code', label: t('stockBar.sortNameCode') },
  ] satisfies Array<{ value: StockBarSortOption; label: string }>, [t]);

  const handleSortChange = useCallback((value: string) => {
    const nextOption = normalizeStockBarSort(value);
    if (!nextOption) return;
    setSortOption(nextOption);
    persistStockBarSort(getStockBarSortStorage(), nextOption);
  }, []);

  const deletableItems = visibleItems;
  const selectedCount = [...selectedCodes].filter((code) => deletableItems.some((item) => item.stockCode === code)).length;
  const allVisibleSelected = deletableItems.length > 0 && selectedCount === deletableItems.length;
  const someVisibleSelected = selectedCount > 0 && !allVisibleSelected;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someVisibleSelected;
    }
  }, [someVisibleSelected]);

  const toggleCode = useCallback((code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedCodes((prev) => {
      const visibleCodes = deletableItems.map((item) => item.stockCode);
      const allSelected = visibleCodes.length > 0 && visibleCodes.every((code) => prev.has(code));
      const next = new Set(prev);
      if (allSelected) {
        visibleCodes.forEach((code) => next.delete(code));
        return next;
      }
      visibleCodes.forEach((code) => next.add(code));
      return next;
    });
  }, [deletableItems]);

  const handleRequestDeleteSelected = useCallback(() => {
    if (!onDeleteStock || selectedCodes.size === 0) return;
    const itemsToDelete = deletableItems.filter((item) => selectedCodes.has(item.stockCode));
    if (itemsToDelete.length === 0) return;
    setPendingDelete({ mode: 'batch', items: itemsToDelete });
  }, [deletableItems, onDeleteStock, selectedCodes]);

  const handleRequestSingleDelete = useCallback((stockCode: string) => {
    const item = items.find((candidate) => candidate.stockCode === stockCode);
    if (!item) return;
    setPendingDelete({ mode: 'single', items: [item] });
  }, [items]);

  const formatDeleteTarget = useCallback((item: StockBarItemType) => {
    const code = item.stockCode;
    const name = item.stockName?.trim();
    if (!name || name === code) return code;
    return language === 'en' ? `${name} (${code})` : `${name}（${code}）`;
  }, [language]);

  const deleteConfirmMessage = useMemo(() => {
    if (!pendingDelete) return '';
    if (pendingDelete.mode === 'single') {
      return t('stockBar.deleteConfirmSingleMessage', {
        target: formatDeleteTarget(pendingDelete.items[0]),
      });
    }

    const previewItems = pendingDelete.items.slice(0, 5);
    const remainingCount = pendingDelete.items.length - previewItems.length;
    const remaining = remainingCount > 0
      ? t('stockBar.deleteConfirmRemaining', { count: remainingCount })
      : '';
    return t('stockBar.deleteConfirmBatchMessage', {
      count: pendingDelete.items.length,
      targets: previewItems.map(formatDeleteTarget).join(language === 'en' ? ', ' : '、'),
      remaining,
    });
  }, [formatDeleteTarget, language, pendingDelete, t]);

  const handleConfirmDelete = useCallback(async () => {
    if (!onDeleteStock || !pendingDelete || isConfirmingDelete) return;
    const codesToDelete = pendingDelete.items.map((item) => item.stockCode);
    setIsConfirmingDelete(true);
    try {
      for (const code of codesToDelete) {
        await onDeleteStock(code);
      }
      setSelectedCodes((prev) => {
        const next = new Set(prev);
        codesToDelete.forEach((code) => next.delete(code));
        return next;
      });
      setPendingDelete(null);
    } finally {
      setIsConfirmingDelete(false);
    }
  }, [isConfirmingDelete, onDeleteStock, pendingDelete]);

  const deleteBusy = isDeleting || isConfirmingDelete;

  return (
    <aside className={`glass-card flex min-h-0 flex-1 flex-col overflow-hidden ${className}`}>
      <ScrollArea
        viewportClassName="p-4 touch-pan-y overscroll-contain"
        testId="home-stock-bar-scroll"
      >
        <div className="mb-4 space-y-3">
          <DashboardPanelHeader
            className="mb-1"
            title={t('stockBar.title')}
            titleClassName="text-sm font-medium"
            leading={(
              <svg className="h-4 w-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            )}
            headingClassName="items-center"
            actions={
              selectedCount > 0 ? (
                <Badge variant="info" size="sm" className="animate-in fade-in zoom-in duration-200">
                  {t('common.selectedCount', { count: selectedCount })}
                </Badge>
              ) : visibleItems.length > 0 ? (
                <span className="text-[11px] text-muted-text">{t('common.itemsCount', { count: visibleItems.length })}</span>
              ) : undefined
            }
          />

          {items.length > 0 ? (
            <input
              type="search"
              value={filterText}
              onChange={(event) => setFilterText(event.target.value)}
              placeholder={t('stockBar.filterPlaceholder')}
              aria-label={t('stockBar.filterAria')}
              className="w-full rounded-lg border border-border/70 bg-elevated/70 px-3 py-2 text-xs text-foreground outline-none transition-colors placeholder:text-muted-text focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
            />
          ) : null}

          {items.length > 0 ? (
            <div className="flex h-9 items-center gap-2">
              <label
                htmlFor={sortId}
                className="flex shrink-0 items-center gap-1.5 text-[11px] font-medium text-muted-text"
              >
                <ArrowUpDown className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{t('stockBar.sortLabel')}</span>
              </label>
              <div className="relative min-w-0 flex-1">
                <select
                  id={sortId}
                  value={sortOption}
                  onChange={(event) => handleSortChange(event.target.value)}
                  className="h-9 w-full appearance-none rounded-lg border border-border/70 bg-elevated/70 py-1.5 pl-3 pr-8 text-xs text-foreground outline-none transition-colors focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
                >
                  {sortOptions.map((option) => (
                    <option key={option.value} value={option.value} className="bg-elevated text-foreground">
                      {option.label}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-text"
                  aria-hidden="true"
                />
              </div>
            </div>
          ) : null}

          {items.length > 0 && onDeleteStock && (
            <div className="flex items-center gap-2">
              <label
                className="flex flex-1 cursor-pointer items-center gap-2 rounded-lg px-2 py-1"
                htmlFor={selectAllId}
              >
                <input
                  id={selectAllId}
                  ref={selectAllRef}
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAll}
                  disabled={deleteBusy}
                  aria-label={t('history.selectAllStockAria')}
                  className="h-3.5 w-3.5 cursor-pointer bg-transparent accent-primary focus:ring-primary/30 disabled:opacity-50"
                />
                <span className="text-[11px] text-muted-text select-none">{t('common.selectAllCurrent')}</span>
              </label>
              <Button
                variant="danger-subtle"
                size="xsm"
                onClick={handleRequestDeleteSelected}
                disabled={selectedCount === 0 || deleteBusy}
                isLoading={deleteBusy}
                className="disabled:!border-transparent disabled:!bg-transparent"
              >
                {deleteBusy ? t('common.deleting') : t('common.delete')}
              </Button>
            </div>
          )}
        </div>

        {isLoading ? (
          <DashboardStateBlock
            loading
            compact
            title={t('stockBar.loading')}
          />
        ) : items.length === 0 ? (
          <DashboardStateBlock
            title={t('stockBar.emptyTitle')}
            description={t('stockBar.emptyDescription')}
            icon={(
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
          />
        ) : visibleItems.length === 0 ? (
          <DashboardStateBlock
            compact
            title={t('stockBar.filterEmptyTitle')}
            description={t('stockBar.filterEmptyDescription')}
          />
        ) : (
          <div className="space-y-1.5">
            {visibleItems.map((item) => {
              const code = item.stockCode || '';
              const isMarket = isMarketReview(code);
              const isSelected = selectedRecordId === item.id || selectedStockCode === code;
              const isChecked = selectedCodes.has(code);

              return (
                <div key={`${code}-${item.id}`} className="flex items-start gap-2 group">
                  {onDeleteStock && (
                    <div className="pt-5">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleCode(code)}
                        disabled={deleteBusy}
                        className="h-3.5 w-3.5 cursor-pointer rounded border-subtle-hover bg-transparent accent-primary focus:ring-primary/30 disabled:opacity-50"
                      />
                    </div>
                  )}
                  <StockBarItemComponent
                    item={item}
                    isViewing={isSelected}
                    onClick={onItemClick}
                    onDelete={onDeleteStock ? handleRequestSingleDelete : undefined}
                    isDeleting={deleteBusy}
                    isMarketReview={isMarket}
                  />
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        title={t('stockBar.deleteConfirmTitle')}
        message={deleteConfirmMessage}
        confirmText={t('stockBar.confirmDelete')}
        confirmDisabled={deleteBusy}
        cancelDisabled={deleteBusy}
        isDanger
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </aside>
  );
};
