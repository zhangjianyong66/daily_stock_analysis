import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../../../api/portfolio';
import type { PortfolioAccountItem } from '../../../types/portfolio';
import { PortfolioImageImportDialog } from '../PortfolioImageImportDialog';

const {
  parsePositionImages,
  commitPositionImages,
  parseTradeImages,
  commitTradeImages,
} = vi.hoisted(() => ({
  parsePositionImages: vi.fn(),
  commitPositionImages: vi.fn(),
  parseTradeImages: vi.fn(),
  commitTradeImages: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    parsePositionImages,
    commitPositionImages,
    parseTradeImages,
    commitTradeImages,
  },
}));

const accounts: PortfolioAccountItem[] = [
  {
    id: 1,
    name: '中国账户',
    broker: '华泰',
    market: 'cn',
    baseCurrency: 'CNY',
    isActive: true,
  },
  {
    id: 2,
    name: '美股账户',
    broker: 'Demo',
    market: 'us',
    baseCurrency: 'USD',
    isActive: true,
  },
];

function renderDialog(overrides: Partial<React.ComponentProps<typeof PortfolioImageImportDialog>> = {}) {
  return render(
    <PortfolioImageImportDialog
      isOpen
      accounts={accounts}
      selectedAccountId={1}
      onClose={vi.fn()}
      onCompleted={vi.fn()}
      {...overrides}
    />,
  );
}

function selectFiles(names: string[]) {
  const files = names.map((name) => new File([name], name, { type: 'image/png' }));
  fireEvent.change(screen.getByLabelText('选择截图'), { target: { files } });
  return files;
}

describe('PortfolioImageImportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    commitPositionImages.mockResolvedValue({
      recordCount: 1,
      insertedCount: 1,
      duplicateCount: 0,
      failedCount: 0,
      errors: [],
    });
    commitTradeImages.mockResolvedValue({
      recordCount: 1,
      insertedCount: 1,
      duplicateCount: 0,
      failedCount: 0,
      errors: [],
    });
  });

  it('switches modes, limits accounts to cn/CNY, and rejects more than five images', () => {
    renderDialog();

    expect(screen.getByRole('button', { name: '持仓初始化' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '成交增量' }));
    expect(screen.getByRole('button', { name: '成交增量' })).toHaveAttribute('aria-pressed', 'true');

    const accountSelect = screen.getByLabelText('导入账户');
    expect(within(accountSelect).getByRole('option', { name: '中国账户' })).toBeInTheDocument();
    expect(within(accountSelect).queryByRole('option', { name: '美股账户' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('批次日期')).toHaveAttribute('max');

    selectFiles(['1.png', '2.png', '3.png', '4.png', '5.png', '6.png']);

    expect(screen.getByText('最多选择 5 张图片')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '识别并校对' })).toBeDisabled();
  });

  it('shows per-file failures and lets the user edit, resolve, and delete position rows', async () => {
    parsePositionImages.mockResolvedValue({
      batchId: 'position-batch',
      accountId: 1,
      snapshotDate: '2026-07-13',
      files: [
        { index: 0, filename: 'positions.png', status: 'success', recordCount: 2, error: null },
        { index: 1, filename: 'broken.png', status: 'failed', recordCount: 0, error: 'invalid_image' },
      ],
      summary: { totalAssets: 100000, availableCash: 20000 },
      positions: [
        {
          sourceRefs: [{ fileIndex: 0, rowIndex: 0 }],
          symbol: '600519',
          name: '贵州茅台',
          quantity: 100,
          avgCost: 1500,
          currentPrice: 1600,
          marketValue: 160000,
          availableQuantity: 80,
          weightPct: 60,
          profitLoss: 10000,
          confidence: 'high',
          status: 'conflict',
          issues: ['position_overlap_conflict'],
        },
        {
          sourceRefs: [{ fileIndex: 0, rowIndex: 1 }],
          symbol: '000001',
          name: '平安银行',
          quantity: 200,
          avgCost: 12,
          currentPrice: 13,
          marketValue: 2600,
          availableQuantity: 200,
          weightPct: 1,
          profitLoss: 200,
          confidence: 'medium',
          status: 'ready',
          issues: [],
        },
      ],
    });
    renderDialog();
    selectFiles(['positions.png', 'broken.png']);

    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));

    await screen.findByText('校对识别结果');
    expect(screen.getByText('broken.png')).toBeInTheDocument();
    expect(screen.getByText('invalid_image')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('贵州茅台 持仓数量'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: '采用 贵州茅台 编辑值' }));
    fireEvent.click(screen.getByRole('button', { name: '移除失败图片 broken.png' }));
    expect(screen.getByRole('button', { name: '确认导入' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: '删除 平安银行' }));
    expect(screen.queryByLabelText('平安银行 持仓数量')).not.toBeInTheDocument();
  });

  it('keeps overlapping trade rows as separate occurrences and commits edited fields', async () => {
    parseTradeImages.mockResolvedValue({
      batchId: 'trade-batch',
      accountId: 1,
      defaultTradeDate: '2026-07-13',
      files: [{ index: 0, filename: 'trades.png', status: 'success', recordCount: 2, error: null }],
      trades: [1, 2].map((rowIndex) => ({
        sourceRefs: [{ fileIndex: 0, rowIndex: rowIndex - 1 }],
        tradeDate: '2026-07-13',
        tradeTime: rowIndex === 1 ? '09:30:05' : null,
        symbol: '600519',
        name: '贵州茅台',
        side: 'buy',
        quantity: 10,
        price: 1500,
        fee: 0,
        tax: 0,
        tradeUid: null,
        confidence: 'high',
        occurrenceIndex: 1,
        fingerprint: 'same-fingerprint',
        dedupHash: null,
        status: 'conflict',
        issues: ['ambiguous_overlap'],
      })),
    });
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: '成交增量' }));
    selectFiles(['trades.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));

    await screen.findByText('校对识别结果');
    fireEvent.click(screen.getByRole('button', { name: '保留 600519 的全部分笔' }));
    fireEvent.change(screen.getAllByLabelText('600519 手续费')[0], { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));

    await waitFor(() => expect(portfolioApi.commitTradeImages).toHaveBeenCalledOnce());
    expect(commitTradeImages).toHaveBeenCalledWith(expect.objectContaining({
      batchId: 'trade-batch',
      accountId: 1,
      trades: [
        expect.objectContaining({ tradeTime: '09:30:05', fee: 5, occurrenceIndex: 1 }),
        expect.objectContaining({ tradeTime: null, occurrenceIndex: 2 }),
      ],
    }));
  });

  it('merges overlapping trade rows into one reviewed record', async () => {
    parseTradeImages.mockResolvedValue({
      batchId: 'trade-batch',
      accountId: 1,
      defaultTradeDate: '2026-07-13',
      files: [{ index: 0, filename: 'trades.png', status: 'success', recordCount: 2, error: null }],
      trades: [0, 1].map((rowIndex) => ({
        sourceRefs: [{ fileIndex: rowIndex, rowIndex: 0 }],
        tradeDate: '2026-07-13',
        tradeTime: '09:30:05',
        symbol: '600519',
        name: '贵州茅台',
        side: 'buy',
        quantity: 10,
        price: 1500,
        fee: 0,
        tax: 0,
        tradeUid: null,
        confidence: 'high',
        occurrenceIndex: 1,
        fingerprint: 'same-fingerprint',
        dedupHash: null,
        status: 'conflict',
        issues: ['ambiguous_overlap'],
      })),
    });
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: '成交增量' }));
    selectFiles(['trades.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));

    await screen.findByText('校对识别结果');
    fireEvent.click(screen.getByRole('button', { name: '合并 600519 为一笔' }));
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));

    await waitFor(() => expect(commitTradeImages).toHaveBeenCalledOnce());
    expect(commitTradeImages.mock.calls[0][0].trades).toHaveLength(1);
  });

  it('revalidates an error position row after editable fields are corrected', async () => {
    parsePositionImages.mockResolvedValue({
      batchId: 'position-error-batch',
      accountId: 1,
      snapshotDate: '2026-07-13',
      files: [{ index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null }],
      summary: {},
      positions: [{
        sourceRefs: [{ fileIndex: 0, rowIndex: 0 }],
        symbol: 'ABC',
        name: '待修正',
        quantity: null,
        avgCost: null,
        currentPrice: null,
        marketValue: null,
        availableQuantity: null,
        weightPct: null,
        profitLoss: null,
        confidence: 'low',
        status: 'error',
        issues: ['invalid_symbol', 'invalid_quantity', 'invalid_avg_cost'],
      }],
    });
    renderDialog();
    selectFiles(['positions.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));

    await screen.findByText('校对识别结果');
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('待修正 证券代码'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('待修正 持仓数量'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('待修正 平均成本'), { target: { value: '1500' } });

    expect(screen.getByRole('button', { name: '确认导入' })).toBeEnabled();
  });

  it('revalidates an error trade row and allows editing its name', async () => {
    parseTradeImages.mockResolvedValue({
      batchId: 'trade-error-batch',
      accountId: 1,
      defaultTradeDate: '2026-07-13',
      files: [{ index: 0, filename: 'trades.png', status: 'success', recordCount: 1, error: null }],
      trades: [{
        sourceRefs: [{ fileIndex: 0, rowIndex: 0 }],
        tradeDate: '2026-07-13',
        tradeTime: '25:00:00',
        symbol: 'ABC',
        name: '待修正',
        side: 'buy',
        quantity: null,
        price: null,
        fee: 0,
        tax: 0,
        tradeUid: null,
        confidence: 'low',
        occurrenceIndex: 1,
        fingerprint: '',
        dedupHash: null,
        status: 'error',
        issues: ['invalid_trade_time', 'invalid_symbol', 'invalid_quantity', 'invalid_price'],
      }],
    });
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: '成交增量' }));
    selectFiles(['trades.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));

    await screen.findByText('校对识别结果');
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('ABC 成交时间'), { target: { value: '10:01:02' } });
    fireEvent.change(screen.getByLabelText('ABC 证券代码'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('600519 成交名称'), { target: { value: '贵州茅台' } });
    fireEvent.change(screen.getByLabelText('600519 成交数量'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('600519 成交价格'), { target: { value: '1500' } });

    expect(screen.getByRole('button', { name: '确认导入' })).toBeEnabled();
  });

  it('reports completion and refreshes the parent after a successful commit', async () => {
    const onCompleted = vi.fn();
    parsePositionImages.mockResolvedValue({
      batchId: 'position-batch',
      accountId: 1,
      snapshotDate: '2026-07-13',
      files: [{ index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null }],
      summary: {},
      positions: [{
        sourceRefs: [{ fileIndex: 0, rowIndex: 0 }],
        symbol: '600519',
        name: '贵州茅台',
        quantity: 100,
        avgCost: 1500,
        currentPrice: null,
        marketValue: null,
        availableQuantity: null,
        weightPct: null,
        profitLoss: null,
        confidence: 'high',
        status: 'ready',
        issues: [],
      }],
    });
    renderDialog({ onCompleted });
    selectFiles(['positions.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));
    await screen.findByText('校对识别结果');

    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));

    await screen.findByText('导入完成');
    expect(screen.getByText('已写入 1 条记录')).toBeInTheDocument();
    expect(onCompleted).toHaveBeenCalledOnce();
  });

  it('disables commit when the reviewed snapshot date is empty or in the future', async () => {
    parsePositionImages.mockResolvedValue({
      batchId: 'position-batch',
      accountId: 1,
      snapshotDate: '2026-07-13',
      files: [{ index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null }],
      summary: {},
      positions: [{
        sourceRefs: [{ fileIndex: 0, rowIndex: 0 }],
        symbol: '600519',
        name: '贵州茅台',
        quantity: 100,
        avgCost: 1500,
        currentPrice: null,
        marketValue: null,
        availableQuantity: null,
        weightPct: null,
        profitLoss: null,
        confidence: 'high',
        status: 'ready',
        issues: [],
      }],
    });
    renderDialog();
    selectFiles(['positions.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));
    await screen.findByText('校对识别结果');
    expect(screen.getByRole('button', { name: '确认导入' })).toBeEnabled();

    fireEvent.change(screen.getByLabelText('快照日期'), { target: { value: '2099-01-01' } });
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('快照日期'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();
  });
});
