import type React from 'react';
import { ChevronRight, Clock3 } from 'lucide-react';
import type { StockBarItem } from '../../types/analysis';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { DashboardStateBlock } from '../dashboard';
import { StockBarItemComponent } from './StockBarItem';

interface MobileStockStripProps {
  items: StockBarItem[];
  isLoading: boolean;
  selectedStockCode?: string;
  selectedRecordId?: number;
  onItemClick: (recordId: number) => void;
  onViewAll: () => void;
}

export const MobileStockStrip: React.FC<MobileStockStripProps> = ({
  items,
  isLoading,
  selectedStockCode,
  selectedRecordId,
  onItemClick,
  onViewAll,
}) => {
  const { t } = useUiLanguage();

  return (
    <section className="border-y border-subtle bg-card/45 py-2 md:hidden" aria-labelledby="mobile-stock-strip-title">
      <div className="flex min-h-11 items-center justify-between gap-3 px-3">
        <div className="flex min-w-0 items-center gap-2">
          <Clock3 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <h2 id="mobile-stock-strip-title" className="truncate text-sm font-semibold text-foreground">
            {t('home.quickAccess')}
          </h2>
        </div>
        <button
          type="button"
          onClick={onViewAll}
          className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-lg px-2 text-xs font-medium text-primary transition-colors hover:bg-hover"
        >
          {t('home.viewAllHistory')}
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {isLoading ? (
        <div className="px-3 pb-1">
          <DashboardStateBlock loading compact title={t('stockBar.loading')} />
        </div>
      ) : items.length > 0 ? (
        <div
          className="flex snap-x snap-mandatory gap-2 overflow-x-auto overscroll-x-contain px-3 pb-1 touch-pan-x"
          data-testid="mobile-stock-strip"
        >
          {items.map((item) => (
            <StockBarItemComponent
              key={`${item.stockCode}-${item.id}`}
              item={item}
              isViewing={selectedRecordId === item.id || selectedStockCode === item.stockCode}
              isMarketReview={item.stockCode === 'MARKET'}
              onClick={onItemClick}
              variant="compact"
              className="w-[10.5rem] flex-none snap-start"
              ariaLabel={t('home.quickAccessItemAria', {
                name: item.stockName || item.stockCode,
                code: item.stockCode,
              })}
            />
          ))}
        </div>
      ) : (
        <p className="px-3 pb-2 text-xs text-muted-text">{t('home.quickAccessEmpty')}</p>
      )}
    </section>
  );
};
