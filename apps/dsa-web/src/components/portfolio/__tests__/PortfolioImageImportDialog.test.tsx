import type React from 'react';
import { useState } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioAccountItem, PortfolioImageTaskSnapshot } from '../../../types/portfolio';
import { PortfolioImageImportDialog } from '../PortfolioImageImportDialog';

const mocks = vi.hoisted(() => ({
  submitPositionImageTask: vi.fn(),
  submitTradeImageTask: vi.fn(),
  getImageTask: vi.fn(),
  updateImageTaskDraft: vi.fn(),
  cancelImageTask: vi.fn(),
  discardImageTask: vi.fn(),
  commitPositionImages: vi.fn(),
  commitTradeImages: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: mocks,
  getExistingPortfolioImageTaskId: () => null,
}));

const accounts: PortfolioAccountItem[] = [
  { id: 1, name: '中国账户', broker: '华泰', market: 'cn', baseCurrency: 'CNY', isActive: true },
  { id: 2, name: '美股账户', broker: 'Demo', market: 'us', baseCurrency: 'USD', isActive: true },
];

const positionRow = {
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
  confidence: 'high' as const,
  status: 'ready' as const,
  issues: [],
};

function positionTask(overrides: Partial<PortfolioImageTaskSnapshot> = {}): PortfolioImageTaskSnapshot {
  return {
    taskId: 'task-position',
    traceId: 'task-position',
    mode: 'positions',
    accountId: 1,
    accountName: '中国账户',
    status: 'review_required',
    message: '识别完成，请校对后确认导入',
    errorCode: null,
    snapshotDate: '2026-07-13',
    defaultTradeDate: null,
    createdAt: '2026-07-14T10:00:00',
    startedAt: '2026-07-14T10:00:01',
    finishedAt: '2026-07-14T10:00:03',
    files: [{ index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null, removed: false }],
    currentFileIndex: 1,
    totalFiles: 1,
    currentAttempt: 1,
    maxAttempts: 2,
    successCount: 1,
    failureCount: 0,
    batchId: 'position-batch',
    draftRevision: 1,
    draft: {
      batchId: 'position-batch',
      accountId: 1,
      snapshotDate: '2026-07-13',
      files: [{ index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null }],
      summary: {},
      positions: [positionRow],
    },
    ...overrides,
  };
}

function Harness({
  initialTask = null,
  onCompleted,
  onTaskChange,
}: {
  initialTask?: PortfolioImageTaskSnapshot | null;
  onCompleted?: React.ComponentProps<typeof PortfolioImageImportDialog>['onCompleted'];
  onTaskChange?: (task: PortfolioImageTaskSnapshot | null) => void;
}) {
  const [task, setTask] = useState<PortfolioImageTaskSnapshot | null>(initialTask);
  return (
    <PortfolioImageImportDialog
      isOpen
      accounts={accounts}
      selectedAccountId={1}
      task={task}
      onClose={vi.fn()}
      onTaskChange={(next) => {
        setTask(next);
        onTaskChange?.(next);
      }}
      onCompleted={onCompleted ?? (() => undefined)}
    />
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
    mocks.commitPositionImages.mockResolvedValue({
      recordCount: 1,
      insertedCount: 1,
      duplicateCount: 0,
      failedCount: 0,
      errors: [],
    });
    mocks.commitTradeImages.mockResolvedValue({
      recordCount: 1,
      insertedCount: 1,
      duplicateCount: 0,
      failedCount: 0,
      errors: [],
    });
  });

  it('限制账户和文件数量，并允许切换导入模式', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: '成交增量' }));
    expect(screen.getByRole('button', { name: '成交增量' })).toHaveAttribute('aria-pressed', 'true');
    const accountSelect = screen.getByLabelText('导入账户');
    expect(within(accountSelect).getByRole('option', { name: '中国账户' })).toBeInTheDocument();
    expect(within(accountSelect).queryByRole('option', { name: '美股账户' })).not.toBeInTheDocument();

    selectFiles(['1.png', '2.png', '3.png', '4.png', '5.png', '6.png']);
    expect(screen.getByText('最多选择 5 张图片')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '识别并校对' })).toBeDisabled();
  });

  it('提交后立即进入后台任务，并允许关闭抽屉', async () => {
    const pending = positionTask({
      status: 'processing',
      message: '正在识别第 1/1 张图片',
      batchId: null,
      draftRevision: null,
      draft: null,
      files: [{ index: 0, filename: 'positions.png', status: 'processing', recordCount: 0, error: null, removed: false }],
    });
    mocks.submitPositionImageTask.mockResolvedValue({
      taskId: pending.taskId,
      traceId: pending.traceId,
      mode: pending.mode,
      accountId: pending.accountId,
      accountName: pending.accountName,
      status: 'pending',
      message: '图片识别任务已创建',
    });
    mocks.getImageTask.mockResolvedValue(pending);
    render(<Harness />);
    selectFiles(['positions.png']);
    fireEvent.click(screen.getByRole('button', { name: '识别并校对' }));

    await waitFor(() => expect(screen.getAllByText('正在识别第 1/1 张图片').length).toBeGreaterThan(0));
    expect(mocks.submitPositionImageTask).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: '关闭' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '取消任务' })).toBeEnabled();
  });

  it('自动保存完整草稿，移除失败文件后携带 task/revision 提交', async () => {
    const review = positionTask({
      files: [
        { index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null, removed: false },
        { index: 1, filename: 'broken.png', status: 'failed', recordCount: 0, error: 'invalid_image', removed: false },
      ],
      totalFiles: 2,
      failureCount: 1,
      draft: {
        batchId: 'position-batch',
        accountId: 1,
        snapshotDate: '2026-07-13',
        files: [
          { index: 0, filename: 'positions.png', status: 'success', recordCount: 1, error: null },
          { index: 1, filename: 'broken.png', status: 'failed', recordCount: 0, error: 'invalid_image' },
        ],
        summary: {},
        positions: [{ ...positionRow, status: 'conflict', issues: ['position_conflict'] }],
      },
    });
    mocks.updateImageTaskDraft.mockImplementation(async (_taskId, request) => positionTask({
      ...review,
      draftRevision: 2,
      files: review.files.map((file) => ({
        ...file,
        removed: request.files.find((item: { index: number }) => item.index === file.index)?.removed ?? false,
      })),
      draft: {
        ...(review.draft as NonNullable<typeof review.draft>),
        positions: request.positions,
      },
    }));
    render(<Harness initialTask={review} />);
    await screen.findByText('校对识别结果');
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('贵州茅台 持仓数量'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: '采用 贵州茅台 编辑值' }));
    fireEvent.click(screen.getByRole('button', { name: '移除失败图片 broken.png' }));

    await waitFor(() => expect(mocks.updateImageTaskDraft).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: '确认导入' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));

    await waitFor(() => expect(mocks.commitPositionImages).toHaveBeenCalledOnce());
    expect(mocks.commitPositionImages).toHaveBeenCalledWith(expect.objectContaining({
      taskId: 'task-position',
      expectedRevision: 2,
      batchId: 'position-batch',
      positions: [expect.objectContaining({ quantity: 120 })],
    }));
  });

  it('processing 取消后展示 cancel_requested 快照', async () => {
    const processing = positionTask({ status: 'processing', draft: null, draftRevision: null, batchId: null });
    const cancelling = { ...processing, status: 'cancel_requested' as const, message: '正在等待当前识别调用结束后取消' };
    mocks.cancelImageTask.mockResolvedValue(cancelling);
    render(<Harness initialTask={processing} />);

    fireEvent.click(await screen.findByRole('button', { name: '取消任务' }));
    await screen.findByRole('button', { name: '等待取消' });
    expect(mocks.cancelImageTask).toHaveBeenCalledWith(processing.taskId);
  });

  it('保存请求进行中继续编辑时会串行保存新版本而不丢失修改', async () => {
    let resolveFirst!: (value: PortfolioImageTaskSnapshot) => void;
    const firstSave = new Promise<PortfolioImageTaskSnapshot>((resolve) => {
      resolveFirst = resolve;
    });
    mocks.updateImageTaskDraft
      .mockImplementationOnce(() => firstSave)
      .mockImplementationOnce(async (_taskId, request) => positionTask({
        draftRevision: 3,
        draft: {
          ...(positionTask().draft as NonNullable<ReturnType<typeof positionTask>['draft']>),
          positions: request.positions,
        },
      }));
    render(<Harness initialTask={positionTask()} />);
    await screen.findByText('校对识别结果');

    fireEvent.change(screen.getByLabelText('贵州茅台 持仓数量'), { target: { value: '110' } });
    await waitFor(() => expect(mocks.updateImageTaskDraft).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('贵州茅台 持仓数量'), { target: { value: '120' } });

    const firstRequest = mocks.updateImageTaskDraft.mock.calls[0][1];
    resolveFirst(positionTask({
      draftRevision: 2,
      draft: {
        ...(positionTask().draft as NonNullable<ReturnType<typeof positionTask>['draft']>),
        positions: firstRequest.positions,
      },
    }));

    await waitFor(() => expect(mocks.updateImageTaskDraft).toHaveBeenCalledTimes(2));
    expect(mocks.updateImageTaskDraft.mock.calls[1][1]).toEqual(expect.objectContaining({
      expectedRevision: 2,
      positions: [expect.objectContaining({ quantity: 120 })],
    }));
  });

  it('草稿 revision 冲突后停止提交并可重新加载服务端版本', async () => {
    const review = positionTask();
    const latest = positionTask({ draftRevision: 2 });
    mocks.updateImageTaskDraft.mockRejectedValue({
      response: { status: 409, data: { error: 'portfolio_image_draft_conflict', message: '草稿冲突' } },
      message: 'Request failed with status code 409',
    });
    mocks.getImageTask.mockResolvedValue(latest);
    render(<Harness initialTask={review} />);

    await screen.findByText('校对识别结果');
    fireEvent.change(screen.getByLabelText('贵州茅台 持仓数量'), { target: { value: '120' } });
    await screen.findByText('草稿版本冲突，请重新加载。');
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重新加载草稿' }));
    await waitFor(() => expect(mocks.getImageTask).toHaveBeenCalledWith(review.taskId));
  });

  it('草稿保存失败后即使 revision 未变化也会重新加载服务端内容', async () => {
    const review = positionTask();
    if (!review.draft || !('positions' in review.draft)) throw new Error('expected positions draft');
    const serverDraft = positionTask({
      draft: {
        ...review.draft,
        positions: [
          {
            ...review.draft.positions[0],
            quantity: 80,
          },
        ],
      },
    });
    mocks.updateImageTaskDraft.mockRejectedValue({
      response: { status: 503, data: { error: 'upstream_unavailable', message: '暂时不可用' } },
      message: 'Request failed with status code 503',
    });
    mocks.getImageTask.mockResolvedValue(serverDraft);
    render(<Harness initialTask={review} />);

    await screen.findByText('校对识别结果');
    fireEvent.change(screen.getByLabelText('贵州茅台 持仓数量'), { target: { value: '120' } });
    await screen.findByText('草稿保存失败，请重试。');
    fireEvent.click(screen.getByRole('button', { name: '重新加载草稿' }));

    await waitFor(() => expect(screen.getByLabelText('贵州茅台 持仓数量')).toHaveValue(80));
  });

  it('提交成功后显示结果并通知父页面刷新', async () => {
    const onCompleted = vi.fn();
    render(<Harness initialTask={positionTask()} onCompleted={onCompleted} />);
    await screen.findByText('校对识别结果');
    await waitFor(() => expect(screen.getByRole('button', { name: '确认导入' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));

    await screen.findByText('导入完成');
    expect(screen.getByText('已写入 1 条记录')).toBeInTheDocument();
    expect(onCompleted).toHaveBeenCalledOnce();
  });
});
