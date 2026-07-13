import type React from 'react';
import { useState, useCallback, useRef, useEffect, useId, useMemo } from 'react';
import { Badge, Button, ScrollArea } from '../common';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
import { StockBarItemComponent } from './StockBarItem';
import type { StockBarItem as StockBarItemType } from '../../types/analysis';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

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

/**
 * 个股栏组件：以股票维度展示历史分析记录，每只股票只显示一条。
 * 大盘复盘可作为 MARKET 项参与展示，并按最近分析时间排序。
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
  const { t } = useUiLanguage();
  const isMarketReview = (code: string) => code === 'MARKET';
  const [filterText, setFilterText] = useState('');
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const selectAllRef = useRef<HTMLInputElement>(null);
  const selectAllId = useId();

  const normalizedFilter = filterText.trim().toLocaleLowerCase();
  const visibleItems = useMemo(() => {
    if (!normalizedFilter) return items;
    return items.filter((item) => {
      const stockCode = String(item.stockCode || '').toLocaleLowerCase();
      const stockName = String(item.stockName || '').toLocaleLowerCase();
      return stockCode.includes(normalizedFilter) || stockName.includes(normalizedFilter);
    });
  }, [items, normalizedFilter]);

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

  const handleDeleteSelected = useCallback(async () => {
    if (!onDeleteStock || selectedCodes.size === 0) return;
    const visibleCodes = new Set(deletableItems.map((item) => item.stockCode));
    const codesToDelete = [...selectedCodes].filter((code) => visibleCodes.has(code));
    for (const code of codesToDelete) {
      await onDeleteStock(code);
    }
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      codesToDelete.forEach((code) => next.delete(code));
      return next;
    });
  }, [deletableItems, onDeleteStock, selectedCodes]);

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
                  disabled={isDeleting}
                  aria-label={t('history.selectAllStockAria')}
                  className="h-3.5 w-3.5 cursor-pointer bg-transparent accent-primary focus:ring-primary/30 disabled:opacity-50"
                />
                <span className="text-[11px] text-muted-text select-none">{t('common.selectAllCurrent')}</span>
              </label>
              <Button
                variant="danger-subtle"
                size="xsm"
                onClick={() => void handleDeleteSelected()}
                disabled={selectedCount === 0 || isDeleting}
                isLoading={isDeleting}
                className="disabled:!border-transparent disabled:!bg-transparent"
              >
                {isDeleting ? t('common.deleting') : t('common.delete')}
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
                        disabled={isDeleting}
                        className="h-3.5 w-3.5 cursor-pointer rounded border-subtle-hover bg-transparent accent-primary focus:ring-primary/30 disabled:opacity-50"
                      />
                    </div>
                  )}
                  <StockBarItemComponent
                    item={item}
                    isViewing={isSelected}
                    onClick={onItemClick}
                    onDelete={onDeleteStock}
                    isDeleting={isDeleting}
                    isMarketReview={isMarket}
                  />
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </aside>
  );
};
