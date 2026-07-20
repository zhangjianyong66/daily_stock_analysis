import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StockBar } from '../StockBar';
import type { StockBarItem } from '../../../types/analysis';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { STOCK_BAR_SORT_STORAGE_KEY } from '../../../utils/stockBarSort';

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
  afterEach(() => {
    window.localStorage.removeItem(UI_LANGUAGE_STORAGE_KEY);
    window.localStorage.removeItem(STOCK_BAR_SORT_STORAGE_KEY);
  });

  it('sorts by recent analysis by default and exposes all five sort options', () => {
    renderStockBar();

    const sortSelect = screen.getByLabelText('排序');
    expect(sortSelect).toHaveValue('recent');
    expect(within(sortSelect).getAllByRole('option').map((option) => option.textContent)).toEqual([
      '最近分析',
      '最早分析',
      '分析次数最多',
      '情绪分最高',
      '名称/代码',
    ]);
    expect(screen.getAllByRole('button', { name: /历史记录$/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
      'Apple AAPL 历史记录',
      '平安银行 000001 历史记录',
      '贵州茅台 600519 历史记录',
    ]);

    fireEvent.change(sortSelect, { target: { value: 'oldest' } });
    expect(screen.getAllByRole('button', { name: /历史记录$/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
      '贵州茅台 600519 历史记录',
      '平安银行 000001 历史记录',
      'Apple AAPL 历史记录',
    ]);

    fireEvent.change(sortSelect, { target: { value: 'most-analyzed' } });
    expect(screen.getAllByRole('button', { name: /历史记录$/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
      'Apple AAPL 历史记录',
      '贵州茅台 600519 历史记录',
      '平安银行 000001 历史记录',
    ]);

    fireEvent.change(sortSelect, { target: { value: 'highest-sentiment' } });
    expect(screen.getAllByRole('button', { name: /历史记录$/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
      'Apple AAPL 历史记录',
      '贵州茅台 600519 历史记录',
      '平安银行 000001 历史记录',
    ]);

    fireEvent.change(sortSelect, { target: { value: 'name-code' } });
    expect(screen.getAllByRole('button', { name: /历史记录$/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
      '贵州茅台 600519 历史记录',
      '平安银行 000001 历史记录',
      'Apple AAPL 历史记录',
    ]);
  });

  it('persists the selected sort and reapplies it when refreshed items change', () => {
    const { rerender, unmount } = renderStockBar();
    fireEvent.change(screen.getByLabelText('排序'), { target: { value: 'most-analyzed' } });

    expect(window.localStorage.getItem(STOCK_BAR_SORT_STORAGE_KEY)).toBe('most-analyzed');

    rerender(
      <StockBar
        items={items.map((item) => (
          item.stockCode === '000001' ? { ...item, analysisCount: 10 } : item
        ))}
        isLoading={false}
        onItemClick={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('排序')).toHaveValue('most-analyzed');
    expect(screen.getAllByRole('button', { name: /历史记录$/ })[0]).toHaveAccessibleName('平安银行 000001 历史记录');

    unmount();
    renderStockBar();
    expect(screen.getByLabelText('排序')).toHaveValue('most-analyzed');
  });

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

  it('requires confirmation before deleting one stock and uses a danger action', async () => {
    const onDeleteStock = vi.fn().mockResolvedValue(undefined);
    renderStockBar({ onDeleteStock });

    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));

    expect(screen.getByRole('heading', { name: '确认删除历史记录' })).toBeInTheDocument();
    expect(screen.getByText('确认删除“贵州茅台（600519）”的全部历史记录吗？删除后不可恢复。')).toBeInTheDocument();
    expect(onDeleteStock).not.toHaveBeenCalled();
    const confirmButton = screen.getByRole('button', { name: '确认删除' });
    expect(confirmButton).toHaveClass('bg-red-500/80');

    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onDeleteStock).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: '确认删除历史记录' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));

    await waitFor(() => expect(onDeleteStock).toHaveBeenCalledTimes(1));
    expect(onDeleteStock).toHaveBeenCalledWith('600519');
  });

  it('previews the first five batch targets, preserves selection on cancel, and deletes only after confirmation', async () => {
    const batchItems: StockBarItem[] = [
      ...items,
      { id: 4, stockCode: 'MSFT', stockName: 'Microsoft', analysisCount: 1 },
      { id: 5, stockCode: 'TSLA', stockName: 'Tesla', analysisCount: 1 },
      { id: 6, stockCode: 'NVDA', stockName: 'NVIDIA', analysisCount: 1 },
    ];
    const onDeleteStock = vi.fn().mockResolvedValue(undefined);
    renderStockBar({ items: batchItems, onDeleteStock });

    fireEvent.click(screen.getByLabelText('全选当前'));
    fireEvent.click(screen.getByRole('button', { name: '删除' }));

    expect(screen.getByText('已选 6')).toBeInTheDocument();
    expect(screen.getByText(/Apple（AAPL）、平安银行（000001）、贵州茅台（600519）、Microsoft（MSFT）、NVIDIA（NVDA），另有 1 项/)).toBeInTheDocument();
    expect(onDeleteStock).not.toHaveBeenCalled();

    const dialogHeading = screen.getByRole('heading', { name: '确认删除历史记录' });
    const dialogOverlay = dialogHeading.parentElement?.parentElement;
    expect(dialogOverlay).not.toBeNull();
    fireEvent.click(dialogOverlay as HTMLElement);
    expect(screen.getByText('已选 6')).toBeInTheDocument();
    expect(onDeleteStock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));

    await waitFor(() => expect(onDeleteStock).toHaveBeenCalledTimes(6));
    expect(onDeleteStock.mock.calls.map(([code]) => code)).toEqual([
      'AAPL',
      '000001',
      '600519',
      'MSFT',
      'NVDA',
      'TSLA',
    ]);
  });

  it('disables confirm and cancel actions while deletion is running', async () => {
    let resolveDelete: (() => void) | undefined;
    const onDeleteStock = vi.fn(() => new Promise<void>((resolve) => {
      resolveDelete = resolve;
    }));
    renderStockBar({ onDeleteStock });

    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '确认删除' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    });

    resolveDelete?.();
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: '确认删除历史记录' })).not.toBeInTheDocument();
    });
  });

  it('renders the delete confirmation in English', () => {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    render(
      <UiLanguageProvider>
        <StockBar
          items={items}
          isLoading={false}
          onItemClick={vi.fn()}
          onDeleteStock={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Delete 贵州茅台 history record' }));

    expect(screen.getByRole('heading', { name: 'Confirm history deletion' })).toBeInTheDocument();
    expect(screen.getByText('Delete all history records for “贵州茅台 (600519)”? This cannot be undone.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm delete' })).toBeInTheDocument();
    expect(screen.getByLabelText('Sort')).toHaveValue('recent');
    expect(screen.getByRole('option', { name: 'Highest sentiment' })).toBeInTheDocument();
  });
});
