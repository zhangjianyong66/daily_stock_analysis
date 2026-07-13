import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StockBar } from '../StockBar';
import type { StockBarItem } from '../../../types/analysis';

const items: StockBarItem[] = [
  {
    id: 1,
    stockCode: '600519',
    stockName: '贵州茅台',
    sentimentScore: 68,
    operationAdvice: '持有',
    analysisCount: 2,
    lastAnalysisTime: '2026-07-10T08:00:00Z',
  },
  {
    id: 2,
    stockCode: '000001',
    stockName: '平安银行',
    sentimentScore: 55,
    operationAdvice: '观望',
    analysisCount: 1,
    lastAnalysisTime: '2026-07-11T08:00:00Z',
  },
  {
    id: 3,
    stockCode: 'AAPL',
    stockName: 'Apple',
    sentimentScore: 72,
    operationAdvice: '买入',
    analysisCount: 3,
    lastAnalysisTime: '2026-07-12T08:00:00Z',
  },
];

function renderStockBar(overrides: Partial<React.ComponentProps<typeof StockBar>> = {}) {
  return render(
    <StockBar
      items={items}
      isLoading={false}
      onItemClick={vi.fn()}
      {...overrides}
    />,
  );
}

describe('StockBar', () => {
  it('filters visible stocks by code or name without changing the loaded list', () => {
    renderStockBar();

    fireEvent.change(screen.getByPlaceholderText('按代码或名称过滤'), { target: { value: '平安' } });

    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(screen.queryByText('贵州茅台')).not.toBeInTheDocument();
    expect(screen.queryByText('Apple')).not.toBeInTheDocument();
    expect(screen.getByText('1只')).toBeInTheDocument();
  });

  it('filters by code case-insensitively and scopes select-all to visible rows', () => {
    const onDeleteStock = vi.fn();
    renderStockBar({ onDeleteStock });

    fireEvent.change(screen.getByPlaceholderText('按代码或名称过滤'), { target: { value: 'aap' } });
    fireEvent.click(screen.getByLabelText('全选当前'));

    expect(screen.getByText('Apple')).toBeInTheDocument();
    expect(screen.getByText('已选 1')).toBeInTheDocument();
    expect(screen.queryByText('贵州茅台')).not.toBeInTheDocument();
  });

  it('shows an empty filtered state and keeps a mobile-scrollable viewport contract', () => {
    const { container } = renderStockBar();

    fireEvent.change(screen.getByPlaceholderText('按代码或名称过滤'), { target: { value: '不存在' } });

    expect(screen.getByText('没有匹配的个股')).toBeInTheDocument();
    expect(screen.getByText('换一个代码或名称再试。')).toBeInTheDocument();

    const aside = container.querySelector('aside');
    expect(aside).toHaveClass('min-h-0', 'flex-1');
    const viewport = screen.getByTestId('home-stock-bar-scroll');
    expect(viewport).toHaveClass('touch-pan-y');
    expect(within(viewport).getByPlaceholderText('按代码或名称过滤')).toBeInTheDocument();
  });
});
