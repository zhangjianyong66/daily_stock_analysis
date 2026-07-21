import type React from 'react';
import { Pin } from 'lucide-react';
import { Badge, Button } from '../common';
import type { StockBarItem as StockBarItemType } from '../../types/analysis';
import { getSentimentColor } from '../../types/analysis';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';
import { formatDateTime } from '../../utils/format';
import { getMarketPhaseSummaryLabel } from '../../utils/marketPhase';
import { truncateStockName } from '../../utils/stockName';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';

interface StockBarItemProps {
  item: StockBarItemType;
  isViewing: boolean;
  isPinned?: boolean;
  onClick: (recordId: number) => void;
  onTogglePin?: (stockCode: string) => void;
  onDelete?: (stockCode: string) => void;
  isDeleting?: boolean;
  isMarketReview?: boolean;
  variant?: 'default' | 'compact';
  className?: string;
  ariaLabel?: string;
}

export const StockBarItemComponent: React.FC<StockBarItemProps> = ({
  item,
  isViewing,
  isPinned = false,
  onClick,
  onTogglePin,
  onDelete,
  isDeleting = false,
  isMarketReview = false,
  variant = 'default',
  className,
  ariaLabel,
}) => {
  const { language, t } = useUiLanguage();
  const sentimentScore = typeof item.sentimentScore === 'number' ? item.sentimentScore : null;
  const sentimentColor = sentimentScore !== null ? getSentimentColor(sentimentScore) : null;
  const stockName = item.stockName || item.stockCode;
  const pinLabel = t(isPinned ? 'stockBar.unpinStock' : 'stockBar.pinStock', {
    name: stockName,
  });
  const actionLabels = buildDecisionActionLabelMap(t);
  const operationLabel = getDecisionActionLabel(
    item.action,
    item.actionLabel,
    item.operationAdvice,
    t('history.sentiment'),
    actionLabels,
  );
  const phaseLabel = getMarketPhaseSummaryLabel(item.marketPhaseSummary, language)
    ?.replace('市场阶段: ', '')
    .replace('市场阶段：', '')
    .replace('Market phase: ', '');
  const isCompact = variant === 'compact';

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onClick(item.id);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick(item.id)}
      onKeyDown={handleKeyDown}
      aria-label={ariaLabel ?? t('history.itemAria', { name: stockName, code: item.stockCode })}
      className={cn(
        'home-history-item w-full min-w-0 flex-1 cursor-pointer text-left group/item focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
        isCompact ? 'min-h-11 p-2' : 'p-2.5',
        isViewing && 'home-history-item-selected',
        className,
      )}
    >
      <div className="relative z-10 flex items-center gap-2.5">
        {isMarketReview ? (
          <div className="w-1 h-8 rounded-full flex-shrink-0 bg-amber-400" style={{ boxShadow: '0 0 10px rgba(251,191,36,0.4)' }} />
        ) : sentimentColor ? (
          <div
            className="w-1 h-8 rounded-full flex-shrink-0"
            style={{
              backgroundColor: sentimentColor,
              boxShadow: `0 0 10px ${sentimentColor}40`,
            }}
          />
        ) : (
          <div className="w-1 h-8 rounded-full flex-shrink-0 bg-subtle" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <span className="block w-full truncate text-sm font-semibold text-foreground tracking-tight">
                {truncateStockName(stockName)}
              </span>
            </div>
            <div className="flex items-center gap-1 shrink-0" data-testid="history-card-actions">
              {isMarketReview ? (
                <Badge
                  variant="default"
                  size="sm"
                  className="shrink-0 shadow-none text-[10px] font-semibold leading-none"
                  style={{
                    color: '#f59e0b',
                    borderColor: 'rgba(245,158,11,0.3)',
                    backgroundColor: 'rgba(245,158,11,0.1)',
                  }}
                >
                  {t('stockBar.market')}
                </Badge>
              ) : sentimentColor ? (
                <Badge
                  variant="default"
                  size="sm"
                  className="home-history-sentiment-badge shrink-0 shadow-none text-[11px] font-semibold leading-none transition-opacity duration-200"
                  style={{
                    color: sentimentColor,
                    borderColor: `${sentimentColor}30`,
                    backgroundColor: `${sentimentColor}10`,
                  }}
                >
                  {operationLabel} {sentimentScore}
                </Badge>
              ) : null}
              {!isCompact && onTogglePin && (
                <Button
                  variant="ghost"
                  size="xsm"
                  onClick={(event) => {
                    event.stopPropagation();
                    onTogglePin(item.stockCode);
                  }}
                  aria-label={pinLabel}
                  aria-pressed={isPinned}
                  title={pinLabel}
                  className={`h-6 w-6 p-0 flex items-center justify-center ${
                    isPinned
                      ? 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                      : 'text-muted-text'
                  }`}
                >
                  <Pin
                    className="h-3.5 w-3.5"
                    fill={isPinned ? 'currentColor' : 'none'}
                    aria-hidden="true"
                  />
                </Button>
              )}
              {!isCompact && onDelete && (
                <Button
                  variant="ghost"
                  size="xsm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(item.stockCode);
                  }}
                  disabled={isDeleting}
                  className="opacity-0 group-hover/item:opacity-100 transition-opacity h-6 w-6 p-0 flex items-center justify-center"
                  aria-label={t('history.deleteRecord', { name: item.stockName || item.stockCode })}
                >
                  <svg className="h-3.5 w-3.5 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </Button>
              )}
            </div>
          </div>
          <div className={cn('mt-1 items-center gap-2', isCompact ? 'flex' : 'flex flex-wrap')} data-testid="history-card-meta">
            <span className="text-[11px] text-secondary-text font-mono">
              {item.stockCode}
            </span>
            {!isCompact && item.lastAnalysisTime && (
              <>
                <span className="w-1 h-1 rounded-full bg-subtle-hover" />
                <span className="text-[11px] text-muted-text">
                  {formatDateTime(item.lastAnalysisTime)}
                </span>
              </>
            )}
            {!isCompact && item.analysisCount > 1 && (
              <>
                <span className="w-1 h-1 rounded-full bg-subtle-hover" />
                <span className="text-[10px] text-muted-text">
                  {t('history.analysisCount', { count: item.analysisCount })}
                </span>
              </>
            )}
            {!isCompact && phaseLabel ? (
              <>
                <span className="w-1 h-1 rounded-full bg-subtle-hover" />
                <Badge variant="default" size="sm" className="shrink-0 shadow-none text-[10px] leading-none">
                  {phaseLabel}
                </Badge>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};
