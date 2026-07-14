import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Images,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { getExistingPortfolioImageTaskId, portfolioApi } from '../../api/portfolio';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  ImageImportCommitResponse,
  PortfolioAccountItem,
  PortfolioImageTaskSnapshot,
  PositionImageItem,
  TradeImageItem,
} from '../../types/portfolio';
import { getTodayIso } from '../../utils/portfolioFormat';
import { ApiErrorAlert, Button, Drawer, InlineAlert, Tooltip } from '../common';

type ImportMode = 'positions' | 'trades';
type ImportPhase = 'select' | 'parsing' | 'review' | 'committing' | 'failed' | 'completed';

type SelectedImage = {
  id: string;
  index: number;
  file?: File;
  filename: string;
  status: 'selected' | 'pending' | 'processing' | 'success' | 'failed' | 'cancelled';
  recordCount: number;
  error: string | null;
  removed: boolean;
};

type PositionReviewRow = PositionImageItem & { clientId: string };
type TradeReviewRow = TradeImageItem & { clientId: string };

interface PortfolioImageImportDialogProps {
  isOpen: boolean;
  accounts: PortfolioAccountItem[];
  selectedAccountId?: number;
  task?: PortfolioImageTaskSnapshot | null;
  onClose: () => void;
  onTaskChange?: (task: PortfolioImageTaskSnapshot | null) => void;
  onCompleted: (result: ImageImportCommitResponse) => void | Promise<void>;
}

const INPUT_CLASS =
  'input-surface input-focus-glow h-10 w-full min-w-0 rounded-lg border bg-transparent px-3 text-sm text-foreground focus:outline-none';
const MAX_FILES = 5;
const POSITION_EDITABLE_ISSUES = new Set(['invalid_symbol', 'missing_name', 'invalid_quantity', 'invalid_avg_cost']);
const TRADE_EDITABLE_ISSUES = new Set([
  'invalid_trade_date',
  'future_trade_date',
  'invalid_trade_time',
  'invalid_symbol',
  'invalid_side',
  'invalid_quantity',
  'invalid_price',
  'invalid_fee',
  'invalid_tax',
]);
const TRADE_BLOCKING_ISSUES = new Set(['not_executed_trade']);

const TEXT = {
  zh: {
    title: '图片导入',
    positions: '持仓初始化',
    trades: '成交增量',
    account: '导入账户',
    snapshotDate: '快照日期',
    batchDate: '批次日期',
    selectImages: '选择截图',
    parse: '识别并校对',
    parsing: '正在识别',
    review: '校对识别结果',
    commit: '确认导入',
    committing: '正在写入',
    completed: '导入完成',
    close: '关闭',
    restart: '继续导入',
    filesLimit: '最多选择 5 张图片',
    filesRequired: '请先选择 1-5 张图片',
    dateInvalid: '日期不能为空且不能晚于今天',
    accountRequired: '请选择可写的 cn/CNY 账户',
    reviewRequired: '请解决失败图片、冲突和字段错误后再提交',
    noRows: '没有可提交的识别记录',
    privacy: '原图仅用于本次识别，不保存到持仓账本或普通日志。',
    positionNotice: '只导入持仓数量与平均成本；总资产、可用资金等资金数据不会导入。',
    tradeNotice: '截图未提供费用时手续费和税费默认为 0；缺少成交编号时只能尽力去重。',
    failedNotice: '识别失败的图片必须移除后才能提交；如需重试，请放弃整批后重新选择图片。',
    inserted: (count: number) => `已写入 ${count} 条记录`,
  },
  en: {
    title: 'Image import',
    positions: 'Initialize positions',
    trades: 'Add executed trades',
    account: 'Account',
    snapshotDate: 'Snapshot date',
    batchDate: 'Batch date',
    selectImages: 'Select screenshots',
    parse: 'Parse and review',
    parsing: 'Parsing',
    review: 'Review parsed records',
    commit: 'Confirm import',
    committing: 'Importing',
    completed: 'Import complete',
    close: 'Close',
    restart: 'Import more',
    filesLimit: 'Select at most 5 images',
    filesRequired: 'Select 1-5 images first',
    dateInvalid: 'Date is required and cannot be in the future',
    accountRequired: 'Select a writable cn/CNY account',
    reviewRequired: 'Resolve failed images, conflicts, and invalid fields before importing',
    noRows: 'No reviewed records to import',
    privacy: 'Images are used only for this request and are not stored in the ledger or normal logs.',
    positionNotice: 'Only position quantity and average cost are imported. Cash and total asset figures are ignored.',
    tradeNotice: 'Missing fees and taxes default to zero. Deduplication is best-effort without a trade id.',
    failedNotice: 'Remove failed images before importing, or discard the batch and resubmit all images.',
    inserted: (count: number) => `${count} record(s) inserted`,
  },
} as const;

function isSupportedAccount(account: PortfolioAccountItem): boolean {
  return account.isActive && account.market === 'cn' && account.baseCurrency.toUpperCase() === 'CNY';
}

function toSelectedImages(files: File[]): SelectedImage[] {
  return files.map((file, index) => ({
    id: `${file.name}-${file.size}-${file.lastModified}-${index}`,
    index,
    file,
    status: 'selected',
    filename: file.name,
    recordCount: 0,
    error: null,
    removed: false,
  }));
}

function isPositive(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function isNonNegative(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function isValidImportDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && value <= getTodayIso();
}

function isValidPosition(row: PositionReviewRow): boolean {
  return /^\d{6}$/.test(row.symbol)
    && row.name.trim().length > 0
    && isPositive(row.quantity)
    && isPositive(row.avgCost)
    && row.status === 'ready';
}

function positionFieldIssues(row: PositionReviewRow): string[] {
  const issues: string[] = [];
  if (!/^\d{6}$/.test(row.symbol)) issues.push('invalid_symbol');
  if (!row.name.trim()) issues.push('missing_name');
  if (!isPositive(row.quantity)) issues.push('invalid_quantity');
  if (!isPositive(row.avgCost)) issues.push('invalid_avg_cost');
  return issues;
}

function revalidatePosition(row: PositionReviewRow): PositionReviewRow {
  const preserved = row.issues.filter((issue) => !POSITION_EDITABLE_ISSUES.has(issue));
  const editable = positionFieldIssues(row);
  return {
    ...row,
    issues: [...preserved, ...editable],
    status: row.status === 'conflict' ? 'conflict' : editable.length > 0 ? 'error' : 'ready',
  };
}

function isValidTradeTime(value: string | null | undefined): boolean {
  return !value || /^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(value);
}

function tradeFieldIssues(row: TradeReviewRow): string[] {
  const issues: string[] = [];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(row.tradeDate)) issues.push('invalid_trade_date');
  else if (row.tradeDate > getTodayIso()) issues.push('future_trade_date');
  if (!isValidTradeTime(row.tradeTime)) issues.push('invalid_trade_time');
  if (!/^\d{6}$/.test(row.symbol)) issues.push('invalid_symbol');
  if (row.side !== 'buy' && row.side !== 'sell') issues.push('invalid_side');
  if (!isPositive(row.quantity)) issues.push('invalid_quantity');
  if (!isPositive(row.price)) issues.push('invalid_price');
  if (!isNonNegative(row.fee)) issues.push('invalid_fee');
  if (!isNonNegative(row.tax)) issues.push('invalid_tax');
  return issues;
}

function revalidateTrade(row: TradeReviewRow): TradeReviewRow {
  const preserved = row.issues.filter((issue) => !TRADE_EDITABLE_ISSUES.has(issue));
  const editable = tradeFieldIssues(row);
  const hasBlockingIssue = preserved.some((issue) => TRADE_BLOCKING_ISSUES.has(issue));
  return {
    ...row,
    issues: [...preserved, ...editable],
    status: row.status === 'conflict'
      ? 'conflict'
      : editable.length > 0 || hasBlockingIssue ? 'error' : 'ready',
  };
}

function isValidTrade(row: TradeReviewRow): boolean {
  return /^\d{6}$/.test(row.symbol)
    && isValidImportDate(row.tradeDate)
    && (row.side === 'buy' || row.side === 'sell')
    && isPositive(row.quantity)
    && isPositive(row.price)
    && isNonNegative(row.fee)
    && isNonNegative(row.tax)
    && row.status === 'ready';
}

function numberValue(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export const PortfolioImageImportDialog: React.FC<PortfolioImageImportDialogProps> = ({
  isOpen,
  accounts,
  selectedAccountId,
  task,
  onClose,
  onTaskChange = () => undefined,
  onCompleted,
}) => {
  const { language } = useUiLanguage();
  const text = TEXT[language];
  const eligibleAccounts = useMemo(() => accounts.filter(isSupportedAccount), [accounts]);
  const defaultAccountId = eligibleAccounts.some((account) => account.id === selectedAccountId)
    ? selectedAccountId
    : eligibleAccounts[0]?.id;
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [mode, setMode] = useState<ImportMode>('positions');
  const [phase, setPhase] = useState<ImportPhase>('select');
  const [accountId, setAccountId] = useState(defaultAccountId ? String(defaultAccountId) : '');
  const [dateValue, setDateValue] = useState(getTodayIso());
  const [images, setImages] = useState<SelectedImage[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<ParsedApiError | null>(null);
  const [batchId, setBatchId] = useState('');
  const [positionRows, setPositionRows] = useState<PositionReviewRow[]>([]);
  const [tradeRows, setTradeRows] = useState<TradeReviewRow[]>([]);
  const [commitResult, setCommitResult] = useState<ImageImportCommitResponse | null>(null);
  const [draftRevision, setDraftRevision] = useState<number | null>(null);
  const [draftDirty, setDraftDirty] = useState(false);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error' | 'conflict'>('idle');
  const draftEditVersionRef = useRef(0);
  const resolvedAccountId = eligibleAccounts.some((account) => String(account.id) === accountId)
    ? accountId
    : defaultAccountId ? String(defaultAccountId) : '';

  useEffect(() => {
    if (!task) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setMode(task.mode);
      setAccountId(String(task.accountId));
      setDateValue(task.mode === 'positions' ? task.snapshotDate ?? getTodayIso() : task.defaultTradeDate ?? getTodayIso());
      const preserveLocalDraft = task.status === 'review_required' && (draftDirty || saveState === 'saving');
      if (!preserveLocalDraft) {
        setImages(task.files.map((file) => ({
          id: `${task.taskId}-${file.index}`,
          index: file.index,
          filename: file.filename ?? `${file.index + 1}`,
          status: file.status,
          recordCount: file.recordCount,
          error: file.error ?? null,
          removed: file.removed,
        })));
      }
      setBatchId(task.batchId ?? '');
      setRequestError(null);
      setFileError(null);

      if (task.status === 'pending' || task.status === 'processing' || task.status === 'cancel_requested') {
        setPhase('parsing');
        return;
      }
      if (task.status === 'committing') {
        setPhase('committing');
        return;
      }
      if (task.status === 'failed' || task.status === 'cancelled') {
        setPhase('failed');
        return;
      }
      if (task.status !== 'review_required' || !task.draft) return;

      setPhase('review');
      if (draftDirty || saveState === 'saving' || task.draftRevision === draftRevision) return;
      setDraftRevision(task.draftRevision ?? null);
      draftEditVersionRef.current = 0;
      if ('positions' in task.draft) {
        setPositionRows(task.draft.positions.map((row, index) => ({ ...row, clientId: `position-${index}` })));
        setTradeRows([]);
      } else {
        setTradeRows(task.draft.trades.map((row, index) => ({ ...row, clientId: `trade-${index}` })));
        setPositionRows([]);
      }
      setSaveState('saved');
    });
    return () => {
      cancelled = true;
    };
  }, [draftDirty, draftRevision, saveState, task]);

  useEffect(() => {
    if (!task || task.status !== 'review_required' || !draftDirty || draftRevision == null) return;
    if (saveState === 'saving' || saveState === 'conflict') return;
    const editVersion = draftEditVersionRef.current;
    const timer = window.setTimeout(() => {
      setSaveState('saving');
      void portfolioApi.updateImageTaskDraft(task.taskId, {
        expectedRevision: draftRevision,
        files: images.map((image) => ({ index: image.index, removed: image.removed })),
        positions: task.mode === 'positions' ? positionRows.map(({ clientId, ...row }) => {
          void clientId;
          return row;
        }) : undefined,
        trades: task.mode === 'trades' ? tradeRows.map(({ clientId, ...row }) => {
          void clientId;
          return row;
        }) : undefined,
      }).then((updated) => {
        setDraftRevision(updated.draftRevision ?? null);
        if (draftEditVersionRef.current === editVersion) {
          setDraftDirty(false);
          setSaveState('saved');
        } else {
          setDraftDirty(true);
          setSaveState('idle');
        }
        onTaskChange(updated);
      }).catch((error) => {
        const status = (error as { response?: { status?: number } } | null)?.response?.status;
        setSaveState(status === 409 ? 'conflict' : 'error');
        setRequestError(getParsedApiError(error));
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [draftDirty, draftRevision, images, onTaskChange, positionRows, saveState, task, tradeRows]);

  const resetReview = () => {
    setPhase('select');
    setImages([]);
    setFileError(null);
    setRequestError(null);
    setBatchId('');
    setPositionRows([]);
    setTradeRows([]);
    setCommitResult(null);
    setDraftRevision(null);
    setDraftDirty(false);
    setSaveState('idle');
    draftEditVersionRef.current = 0;
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const changeMode = (nextMode: ImportMode) => {
    if (task || phase === 'parsing' || phase === 'committing') return;
    setMode(nextMode);
    setDateValue(getTodayIso());
    resetReview();
  };

  const handleFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    setRequestError(null);
    setPositionRows([]);
    setTradeRows([]);
    setBatchId('');
    setCommitResult(null);
    setPhase('select');
    if (nextFiles.length > MAX_FILES) {
      setImages([]);
      setFileError(text.filesLimit);
      return;
    }
    setImages(toSelectedImages(nextFiles));
    setFileError(nextFiles.length === 0 ? text.filesRequired : null);
  };

  const handleParse = async () => {
    const parsedAccountId = Number(resolvedAccountId);
    if (!eligibleAccounts.some((account) => account.id === parsedAccountId)) {
      setFileError(text.accountRequired);
      return;
    }
    if (images.length === 0 || images.length > MAX_FILES) {
      setFileError(images.length > MAX_FILES ? text.filesLimit : text.filesRequired);
      return;
    }
    if (!isValidImportDate(dateValue)) {
      setFileError(text.dateInvalid);
      return;
    }

    setPhase('parsing');
    setFileError(null);
    setRequestError(null);
    try {
      const files = images.map((item) => item.file).filter((file): file is File => Boolean(file));
      const accepted = mode === 'positions'
        ? await portfolioApi.submitPositionImageTask(parsedAccountId, dateValue, files)
        : await portfolioApi.submitTradeImageTask(parsedAccountId, dateValue, files);
      const snapshot = await portfolioApi.getImageTask(accepted.taskId);
      onTaskChange(snapshot);
      setPhase('parsing');
    } catch (error) {
      const existingTaskId = getExistingPortfolioImageTaskId(error);
      if (existingTaskId) {
        try {
          const existing = await portfolioApi.getImageTask(existingTaskId);
          onTaskChange(existing);
          setPhase(existing.status === 'review_required' ? 'review' : 'parsing');
          return;
        } catch (loadError) {
          setRequestError(getParsedApiError(loadError));
        }
      } else {
        setRequestError(getParsedApiError(error));
      }
      setPhase('select');
    }
  };

  const removeImage = (id: string) => {
    if (!task) {
      setImages((current) => current.filter((image) => image.id !== id));
      return;
    }
    setImages((current) => current.map((image) => (
      image.id === id ? { ...image, removed: true } : image
    )));
    markDraftDirty();
  };

  const markDraftDirty = () => {
    draftEditVersionRef.current += 1;
    setDraftDirty(true);
    setSaveState((current) => current === 'saving' ? current : 'idle');
  };

  const updatePosition = <K extends keyof PositionReviewRow>(clientId: string, field: K, value: PositionReviewRow[K]) => {
    setPositionRows((current) => current.map((row) => (
      row.clientId === clientId ? revalidatePosition({ ...row, [field]: value }) : row
    )));
    markDraftDirty();
  };

  const updateTrade = <K extends keyof TradeReviewRow>(clientId: string, field: K, value: TradeReviewRow[K]) => {
    setTradeRows((current) => current.map((row) => (
      row.clientId === clientId ? revalidateTrade({ ...row, [field]: value }) : row
    )));
    markDraftDirty();
  };

  const adoptPosition = (clientId: string) => {
    setPositionRows((current) => current.map((row) => {
      if (row.clientId !== clientId) return row;
      return revalidatePosition({
        ...row,
        status: 'ready',
        issues: row.issues.filter((issue) => !issue.includes('conflict')),
      });
    }));
    markDraftDirty();
  };

  const adoptTrade = (clientId: string) => {
    setTradeRows((current) => current.map((row) => {
      if (row.clientId !== clientId) return row;
      return revalidateTrade({
        ...row,
        status: 'ready',
        issues: row.issues.filter((issue) => !issue.includes('conflict') && issue !== 'ambiguous_overlap'),
      });
    }));
    markDraftDirty();
  };

  const keepTradeGroup = (fingerprint: string) => {
    let occurrenceIndex = 0;
    setTradeRows((current) => current.map((row) => {
      if (row.fingerprint !== fingerprint) return row;
      occurrenceIndex += 1;
      return {
        ...row,
        status: 'ready',
        issues: row.issues.filter((issue) => issue !== 'ambiguous_overlap'),
        occurrenceIndex,
      };
    }));
    markDraftDirty();
  };

  const mergeTradeGroup = (fingerprint: string, keepClientId: string) => {
    setTradeRows((current) => current
      .filter((row) => row.fingerprint !== fingerprint || row.clientId === keepClientId)
      .map((row) => (
        row.clientId === keepClientId
          ? {
            ...row,
            status: 'ready' as const,
            issues: row.issues.filter((issue) => issue !== 'ambiguous_overlap'),
            occurrenceIndex: 1,
          }
          : row
      )));
    markDraftDirty();
  };

  const hasFailedImages = images.some((image) => !image.removed && (image.status === 'failed' || image.status === 'selected'));
  const reviewRows = mode === 'positions' ? positionRows : tradeRows;
  const hasValidRows = reviewRows.length > 0;
  const rowsAreValid = mode === 'positions'
    ? positionRows.every(isValidPosition)
    : tradeRows.every(isValidTrade);
  const commitDateIsValid = mode === 'trades' || isValidImportDate(dateValue);
  const canCommit = phase === 'review'
    && Boolean(task)
    && draftRevision != null
    && !draftDirty
    && saveState !== 'saving'
    && saveState !== 'error'
    && saveState !== 'conflict'
    && !hasFailedImages
    && hasValidRows
    && rowsAreValid
    && commitDateIsValid;

  const handleCommit = async () => {
    if (!canCommit) {
      setFileError(hasValidRows ? text.reviewRequired : text.noRows);
      return;
    }
    if (!task || draftRevision == null) return;
    const parsedAccountId = task.accountId;
    setPhase('committing');
    setRequestError(null);
    try {
      const result = mode === 'positions'
        ? await portfolioApi.commitPositionImages({
          batchId,
          accountId: parsedAccountId,
          snapshotDate: dateValue,
          taskId: task.taskId,
          expectedRevision: draftRevision,
          positions: positionRows.map((row) => ({
            symbol: row.symbol,
            name: row.name,
            quantity: row.quantity as number,
            avgCost: row.avgCost as number,
          })),
        })
        : await portfolioApi.commitTradeImages({
          batchId,
          accountId: parsedAccountId,
          taskId: task.taskId,
          expectedRevision: draftRevision,
          trades: tradeRows.map((row) => ({
            tradeDate: row.tradeDate,
            tradeTime: row.tradeTime ?? null,
            symbol: row.symbol,
            name: row.name || null,
            side: row.side as 'buy' | 'sell',
            quantity: row.quantity as number,
            price: row.price as number,
            fee: row.fee,
            tax: row.tax,
            tradeUid: row.tradeUid ?? null,
            occurrenceIndex: row.occurrenceIndex,
          })),
        });
      setCommitResult(result);
      setPhase('completed');
      onTaskChange(null);
      await onCompleted(result);
    } catch (error) {
      setRequestError(getParsedApiError(error));
      setPhase('review');
    }
  };

  const handleCancel = async () => {
    if (!task) return;
    try {
      onTaskChange(await portfolioApi.cancelImageTask(task.taskId));
    } catch (error) {
      setRequestError(getParsedApiError(error));
    }
  };

  const handleDiscard = async () => {
    if (!task) return;
    try {
      await portfolioApi.discardImageTask(task.taskId);
      onTaskChange(null);
      resetReview();
    } catch (error) {
      setRequestError(getParsedApiError(error));
    }
  };

  const reloadDraft = async () => {
    if (!task) return;
    try {
      const latestTask = await portfolioApi.getImageTask(task.taskId);
      setDraftDirty(false);
      setSaveState('idle');
      setDraftRevision(null);
      draftEditVersionRef.current = 0;
      onTaskChange(latestTask);
    } catch (error) {
      setRequestError(getParsedApiError(error));
    }
  };

  const deletePositionRow = (clientId: string) => {
    setPositionRows((current) => current.filter((row) => row.clientId !== clientId));
    markDraftDirty();
  };

  const deleteTradeRow = (clientId: string) => {
    setTradeRows((current) => current.filter((row) => row.clientId !== clientId));
    markDraftDirty();
  };

  const isBusy = phase === 'committing';
  const taskLocked = Boolean(task);

  return (
    <Drawer
      isOpen={isOpen}
      onClose={isBusy ? () => undefined : onClose}
      title={text.title}
      width="max-w-6xl"
    >
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-1 rounded-lg border border-border/70 bg-muted/20 p-1" role="group" aria-label="导入模式">
          <button
            type="button"
            aria-pressed={mode === 'positions'}
            className={`h-10 rounded-md px-3 text-sm font-medium transition ${mode === 'positions' ? 'bg-card text-foreground shadow-sm' : 'text-secondary-text hover:text-foreground'}`}
            onClick={() => changeMode('positions')}
            disabled={isBusy || taskLocked}
          >
            {text.positions}
          </button>
          <button
            type="button"
            aria-pressed={mode === 'trades'}
            className={`h-10 rounded-md px-3 text-sm font-medium transition ${mode === 'trades' ? 'bg-card text-foreground shadow-sm' : 'text-secondary-text hover:text-foreground'}`}
            onClick={() => changeMode('trades')}
            disabled={isBusy || taskLocked}
          >
            {text.trades}
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm font-medium text-foreground">
            <span className="mb-2 block">{text.account}</span>
            <select
              className={INPUT_CLASS}
              aria-label={text.account}
              value={resolvedAccountId}
              onChange={(event) => setAccountId(event.target.value)}
              disabled={isBusy || taskLocked || phase === 'completed'}
            >
              {eligibleAccounts.length === 0 ? <option value="">{text.accountRequired}</option> : null}
              {eligibleAccounts.map((account) => (
                <option key={account.id} value={account.id}>{account.name}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-foreground">
            <span className="mb-2 block">{mode === 'positions' ? text.snapshotDate : text.batchDate}</span>
            <input
              aria-label={mode === 'positions' ? text.snapshotDate : text.batchDate}
              type="date"
              max={getTodayIso()}
              value={dateValue}
              onChange={(event) => setDateValue(event.target.value)}
              disabled={isBusy || taskLocked || phase === 'completed'}
              className={INPUT_CLASS}
            />
          </label>
        </div>

        <InlineAlert
          variant="info"
          message={<div className="space-y-1"><p>{mode === 'positions' ? text.positionNotice : text.tradeNotice}</p><p>{text.privacy}</p></div>}
          className="!rounded-lg"
        />

        {phase !== 'completed' ? (
          <section className="border-y border-border/60 py-4" aria-label="图片文件">
            {!task ? <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-cyan/30 px-4 text-sm font-medium text-cyan transition hover:bg-cyan/10">
                <Images className="h-4 w-4" />
                {text.selectImages}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  multiple
                  className="sr-only"
                  aria-label={text.selectImages}
                  onChange={handleFiles}
                  disabled={isBusy || taskLocked}
                />
              </label>
              <span className="text-xs text-secondary-text">{images.length}/{MAX_FILES}</span>
            </div> : null}

            {images.length > 0 ? (
              <div className="mt-4 divide-y divide-border/50 border-y border-border/50">
                {images.map((image) => (
                  <div key={image.id} className={`flex min-w-0 items-center gap-3 py-3 ${image.removed ? 'opacity-50' : ''}`}>
                    {image.status === 'success' ? <CheckCircle2 className="h-4 w-4 shrink-0 text-success" /> : null}
                    {image.status === 'failed' ? <AlertTriangle className="h-4 w-4 shrink-0 text-danger" /> : null}
                    {image.status === 'selected' || image.status === 'pending' || image.status === 'processing' ? <Upload className="h-4 w-4 shrink-0 text-secondary-text" /> : null}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{image.filename}</p>
                      <p className="mt-0.5 break-words text-xs text-secondary-text">
                        {image.removed ? '已从本次草稿移除' : image.error ?? (image.status === 'success' ? `${image.recordCount} 条记录` : task?.message ?? '等待识别')}
                      </p>
                    </div>
                    {(!task || (task.status === 'review_required' && image.status === 'failed' && !image.removed)) ? <Tooltip content="移除图片">
                      <button
                        type="button"
                        className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 text-secondary-text hover:border-danger/50 hover:text-danger"
                        aria-label={image.status === 'failed' ? `移除失败图片 ${image.filename}` : `移除图片 ${image.filename}`}
                        onClick={() => removeImage(image.id)}
                        disabled={isBusy}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </Tooltip> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}

        {fileError ? <InlineAlert variant="danger" message={fileError} className="!rounded-lg" /> : null}
        {requestError ? <ApiErrorAlert error={requestError} /> : null}
        {phase === 'parsing' && task ? (
          <InlineAlert variant="info" message={task.message} className="!rounded-lg" />
        ) : null}
        {phase === 'failed' && task ? (
          <InlineAlert variant="danger" message={task.message} className="!rounded-lg" />
        ) : null}
        {images.some((image) => image.status === 'failed' && !image.removed) ? (
          <InlineAlert variant="warning" message={text.failedNotice} className="!rounded-lg" />
        ) : null}

        {phase === 'review' || phase === 'committing' ? (
          <section aria-labelledby="portfolio-image-review-title">
            <h3 id="portfolio-image-review-title" className="text-base font-semibold text-foreground">{text.review}</h3>
            <p className="mt-1 text-xs text-secondary-text">
              {saveState === 'saving' ? '正在保存草稿…' : saveState === 'saved' ? `草稿已保存（版本 ${draftRevision ?? '-'}）` : saveState === 'conflict' ? '草稿版本冲突，请重新加载。' : saveState === 'error' ? '草稿保存失败，请重试。' : '编辑后将自动保存草稿。'}
            </p>
            {saveState === 'conflict' || saveState === 'error' ? (
              <Button size="sm" variant="outline" className="mt-2" onClick={() => void reloadDraft()}>
                <RefreshCw className="h-4 w-4" />重新加载草稿
              </Button>
            ) : null}
            {mode === 'positions' ? (
              <PositionReview
                rows={positionRows}
                disabled={isBusy}
                onUpdate={updatePosition}
                onDelete={deletePositionRow}
                onAdopt={adoptPosition}
              />
            ) : (
              <TradeReview
                rows={tradeRows}
                disabled={isBusy}
                onUpdate={updateTrade}
                onDelete={deleteTradeRow}
                onKeepGroup={keepTradeGroup}
                onMergeGroup={mergeTradeGroup}
                onAdopt={adoptTrade}
              />
            )}
          </section>
        ) : null}

        {phase === 'completed' && commitResult ? (
          <section className="border-y border-border/60 py-8 text-center">
            <CheckCircle2 className="mx-auto h-10 w-10 text-success" />
            <h3 className="mt-3 text-lg font-semibold text-foreground">{text.completed}</h3>
            <p className="mt-2 text-sm text-secondary-text">{text.inserted(commitResult.insertedCount)}</p>
            {commitResult.duplicateCount > 0 ? (
              <p className="mt-1 text-xs text-secondary-text">已跳过 {commitResult.duplicateCount} 条重复记录</p>
            ) : null}
          </section>
        ) : null}

        <div className="flex flex-col-reverse gap-3 border-t border-border/60 pt-4 sm:flex-row sm:justify-end">
          {phase === 'completed' ? (
            <>
              <Button variant="secondary" onClick={onClose}>{text.close}</Button>
              <Button onClick={resetReview}><RefreshCw className="h-4 w-4" />{text.restart}</Button>
            </>
          ) : phase === 'parsing' && task ? (
            <>
              <Button variant="secondary" onClick={onClose}>{text.close}</Button>
              <Button variant="outline" onClick={() => void handleCancel()} disabled={task.status === 'cancel_requested'}>
                {task.status === 'cancel_requested' ? '等待取消' : '取消任务'}
              </Button>
            </>
          ) : phase === 'failed' && task ? (
            <>
              <Button variant="secondary" onClick={onClose}>{text.close}</Button>
              <Button onClick={() => void handleDiscard()}><RefreshCw className="h-4 w-4" />清除并重新选择</Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={onClose} disabled={isBusy}>{text.close}</Button>
              {phase === 'select' ? (
                <Button
                  onClick={() => void handleParse()}
                  disabled={images.length === 0 || Boolean(fileError) || !resolvedAccountId || !isValidImportDate(dateValue)}
                >
                  <Upload className="h-4 w-4" />{text.parse}
                </Button>
              ) : (
                <>
                  {phase === 'review' && task ? <Button variant="outline" onClick={() => void handleDiscard()}>放弃本次识别</Button> : null}
                  <Button
                    onClick={() => void handleCommit()}
                    isLoading={phase === 'committing'}
                    loadingText={text.committing}
                    disabled={!canCommit}
                  >
                    <CheckCircle2 className="h-4 w-4" />{text.commit}
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </Drawer>
  );
};

interface PositionReviewProps {
  rows: PositionReviewRow[];
  disabled: boolean;
  onUpdate: <K extends keyof PositionReviewRow>(clientId: string, field: K, value: PositionReviewRow[K]) => void;
  onDelete: (clientId: string) => void;
  onAdopt: (clientId: string) => void;
}

const PositionReview: React.FC<PositionReviewProps> = ({ rows, disabled, onUpdate, onDelete, onAdopt }) => (
  <div className="mt-3 divide-y divide-border/50 border-y border-border/60" role="table" aria-label="持仓识别结果">
    {rows.map((row) => (
      <div key={row.clientId} className="grid gap-3 py-4 lg:grid-cols-[8rem_minmax(10rem,1fr)_7rem_7rem_auto] lg:items-end" role="row">
        <label className="text-xs text-secondary-text">
          证券代码
          <input
            className={`${INPUT_CLASS} mt-1`}
            value={row.symbol}
            onChange={(event) => onUpdate(row.clientId, 'symbol', event.target.value)}
            disabled={disabled}
            aria-label={`${row.name} 证券代码`}
          />
        </label>
        <label className="text-xs text-secondary-text">
          名称
          <input
            className={`${INPUT_CLASS} mt-1`}
            value={row.name}
            onChange={(event) => onUpdate(row.clientId, 'name', event.target.value)}
            disabled={disabled}
            aria-label={`${row.name} 名称`}
          />
        </label>
        <label className="text-xs text-secondary-text">
          持仓数量
          <input
            className={`${INPUT_CLASS} mt-1`}
            type="number"
            min="0"
            value={row.quantity ?? ''}
            onChange={(event) => onUpdate(row.clientId, 'quantity', numberValue(event.target.value))}
            disabled={disabled}
            aria-label={`${row.name} 持仓数量`}
          />
        </label>
        <label className="text-xs text-secondary-text">
          平均成本
          <input
            className={`${INPUT_CLASS} mt-1`}
            type="number"
            min="0"
            step="0.0001"
            value={row.avgCost ?? ''}
            onChange={(event) => onUpdate(row.clientId, 'avgCost', numberValue(event.target.value))}
            disabled={disabled}
            aria-label={`${row.name} 平均成本`}
          />
        </label>
        <div className="flex items-center justify-end gap-2">
          {row.status === 'conflict' ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onAdopt(row.clientId)}
              disabled={disabled}
              aria-label={`采用 ${row.name} 编辑值`}
            >
              采用编辑值
            </Button>
          ) : null}
          <Tooltip content="删除此行">
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 text-secondary-text hover:border-danger/50 hover:text-danger"
              aria-label={`删除 ${row.name}`}
              onClick={() => onDelete(row.clientId)}
              disabled={disabled}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </Tooltip>
        </div>
        {row.issues.length > 0 ? (
          <p className="text-xs text-warning lg:col-span-full">{row.issues.join('；')}</p>
        ) : null}
      </div>
    ))}
  </div>
);

interface TradeReviewProps {
  rows: TradeReviewRow[];
  disabled: boolean;
  onUpdate: <K extends keyof TradeReviewRow>(clientId: string, field: K, value: TradeReviewRow[K]) => void;
  onDelete: (clientId: string) => void;
  onKeepGroup: (fingerprint: string) => void;
  onMergeGroup: (fingerprint: string, keepClientId: string) => void;
  onAdopt: (clientId: string) => void;
}

const TradeReview: React.FC<TradeReviewProps> = ({
  rows,
  disabled,
  onUpdate,
  onDelete,
  onKeepGroup,
  onMergeGroup,
  onAdopt,
}) => (
  <div className="mt-3 divide-y divide-border/50 border-y border-border/60" role="table" aria-label="成交识别结果">
    {rows.map((row, rowIndex) => {
      const groupRows = rows.filter((item) => item.fingerprint === row.fingerprint);
      const isFirstInGroup = rows.findIndex((item) => item.fingerprint === row.fingerprint) === rowIndex;
      const isOverlapGroup = row.status === 'conflict' && groupRows.length > 1;
      return (
        <div key={row.clientId} className="grid gap-3 py-4 lg:grid-cols-4 xl:grid-cols-9" role="row">
          <label className="text-xs text-secondary-text">日期
            <input className={`${INPUT_CLASS} mt-1`} type="date" max={getTodayIso()} value={row.tradeDate} onChange={(event) => onUpdate(row.clientId, 'tradeDate', event.target.value)} disabled={disabled} aria-label={`${row.symbol} 成交日期`} />
          </label>
          <label className="text-xs text-secondary-text">时间
            <input className={`${INPUT_CLASS} mt-1`} type="time" step="1" value={row.tradeTime ?? ''} onChange={(event) => onUpdate(row.clientId, 'tradeTime', event.target.value || null)} disabled={disabled} aria-label={`${row.symbol} 成交时间`} />
          </label>
          <label className="text-xs text-secondary-text">证券代码
            <input className={`${INPUT_CLASS} mt-1`} value={row.symbol} onChange={(event) => onUpdate(row.clientId, 'symbol', event.target.value)} disabled={disabled} aria-label={`${row.symbol} 证券代码`} />
          </label>
          <label className="text-xs text-secondary-text">名称
            <input className={`${INPUT_CLASS} mt-1`} value={row.name ?? ''} onChange={(event) => onUpdate(row.clientId, 'name', event.target.value)} disabled={disabled} aria-label={`${row.symbol} 成交名称`} />
          </label>
          <label className="text-xs text-secondary-text">方向
            <select className={`${INPUT_CLASS} mt-1`} value={row.side} onChange={(event) => onUpdate(row.clientId, 'side', event.target.value)} disabled={disabled} aria-label={`${row.symbol} 成交方向`}>
              <option value="buy">买入</option>
              <option value="sell">卖出</option>
            </select>
          </label>
          <label className="text-xs text-secondary-text">数量
            <input className={`${INPUT_CLASS} mt-1`} type="number" min="0" value={row.quantity ?? ''} onChange={(event) => onUpdate(row.clientId, 'quantity', numberValue(event.target.value))} disabled={disabled} aria-label={`${row.symbol} 成交数量`} />
          </label>
          <label className="text-xs text-secondary-text">价格
            <input className={`${INPUT_CLASS} mt-1`} type="number" min="0" step="0.0001" value={row.price ?? ''} onChange={(event) => onUpdate(row.clientId, 'price', numberValue(event.target.value))} disabled={disabled} aria-label={`${row.symbol} 成交价格`} />
          </label>
          <label className="text-xs text-secondary-text">手续费
            <input className={`${INPUT_CLASS} mt-1`} type="number" min="0" step="0.01" value={row.fee} onChange={(event) => onUpdate(row.clientId, 'fee', numberValue(event.target.value) ?? 0)} disabled={disabled} aria-label={`${row.symbol} 手续费`} />
          </label>
          <label className="text-xs text-secondary-text">税费
            <input className={`${INPUT_CLASS} mt-1`} type="number" min="0" step="0.01" value={row.tax} onChange={(event) => onUpdate(row.clientId, 'tax', numberValue(event.target.value) ?? 0)} disabled={disabled} aria-label={`${row.symbol} 税费`} />
          </label>
          <div className="flex flex-wrap items-center justify-between gap-2 lg:col-span-4 xl:col-span-9">
            <div className="min-w-0 text-xs text-secondary-text">
              <span>{row.name || row.symbol}</span>
              {row.issues.length > 0 ? <span className="ml-2 text-warning">{row.issues.join('；')}</span> : null}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              {isOverlapGroup && isFirstInGroup ? (
                <>
                  <Button size="sm" variant="outline" onClick={() => onMergeGroup(row.fingerprint, row.clientId)} disabled={disabled} aria-label={`合并 ${row.symbol} 为一笔`}>
                    合并一笔
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => onKeepGroup(row.fingerprint)} disabled={disabled} aria-label={`保留 ${row.symbol} 的全部分笔`}>
                    保留多笔
                  </Button>
                </>
              ) : null}
              {row.status === 'conflict' && !isOverlapGroup ? (
                <Button size="sm" variant="outline" onClick={() => onAdopt(row.clientId)} disabled={disabled}>采用编辑值</Button>
              ) : null}
              <Tooltip content="删除此行">
                <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 text-secondary-text hover:border-danger/50 hover:text-danger" aria-label={`删除 ${row.symbol} 第 ${rowIndex + 1} 行`} onClick={() => onDelete(row.clientId)} disabled={disabled}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </Tooltip>
            </div>
          </div>
        </div>
      );
    })}
  </div>
);
