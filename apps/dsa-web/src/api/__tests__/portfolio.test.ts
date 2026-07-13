import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../portfolio';
import type {
  PositionImageCommitRequest,
  PortfolioTradeCreateRequest,
  TradeImageCommitRequest,
} from '../../types/portfolio';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: {
    get,
    post,
  },
}));

describe('portfolioApi trade time contract', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('maps tradeTime to trade_time when creating a trade', async () => {
    post.mockResolvedValueOnce({ data: { id: 1 } });
    const payload = {
      accountId: 1,
      symbol: '600519',
      tradeDate: '2026-01-02',
      tradeTime: '09:30:05',
      side: 'buy',
      quantity: 10,
      price: 100,
    } as PortfolioTradeCreateRequest & { tradeTime: string };

    await portfolioApi.createTrade(payload);

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/trades', expect.objectContaining({
      trade_date: '2026-01-02',
      trade_time: '09:30:05',
    }));
  });

  it('maps nullable trade_time from list responses', async () => {
    get.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 1,
            account_id: 1,
            trade_uid: null,
            symbol: '600519',
            market: 'cn',
            currency: 'CNY',
            trade_date: '2026-01-02',
            trade_time: '09:30:05',
            side: 'buy',
            quantity: 10,
            price: 100,
            fee: 0,
            tax: 0,
            note: null,
            created_at: null,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      },
    });

    const result = await portfolioApi.listTrades({ accountId: 1 });

    expect(result.items[0].tradeTime).toBe('09:30:05');
  });
});

describe('portfolioApi image import contract', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('posts repeated files and maps a position parse response to camelCase', async () => {
    post.mockResolvedValueOnce({
      data: {
        batch_id: 'position-batch',
        account_id: 7,
        snapshot_date: '2026-07-13',
        files: [
          { index: 0, filename: 'one.png', status: 'success', record_count: 1, error: null },
          { index: 1, filename: 'two.png', status: 'failed', record_count: 0, error: 'invalid_image' },
        ],
        summary: { total_assets: 12000, available_cash: 2000 },
        positions: [{
          source_refs: [{ file_index: 0, row_index: 0 }],
          symbol: '600519',
          name: '贵州茅台',
          quantity: 100,
          avg_cost: 1500,
          current_price: 1600,
          market_value: 160000,
          available_quantity: 80,
          weight_pct: 50,
          profit_loss: 10000,
          confidence: 'high',
          status: 'ready',
          issues: [],
        }],
      },
    });
    const files = [
      new File(['one'], 'one.png', { type: 'image/png' }),
      new File(['two'], 'two.png', { type: 'image/png' }),
    ];

    const result = await portfolioApi.parsePositionImages(7, '2026-07-13', files);

    expect(post).toHaveBeenCalledOnce();
    const [path, body, config] = post.mock.calls[0];
    expect(path).toBe('/api/v1/portfolio/imports/images/positions/parse');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('account_id')).toBe('7');
    expect((body as FormData).get('snapshot_date')).toBe('2026-07-13');
    expect((body as FormData).getAll('files')).toEqual(files);
    expect(config).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } });
    expect(result.positions[0].sourceRefs[0]).toEqual({ fileIndex: 0, rowIndex: 0 });
    expect(result.positions[0].avgCost).toBe(1500);
    expect(result.summary.availableCash).toBe(2000);
  });

  it('commits reviewed positions as snake_case JSON', async () => {
    post.mockResolvedValueOnce({
      data: { record_count: 1, inserted_count: 1, duplicate_count: 0, failed_count: 0, errors: [] },
    });
    const request: PositionImageCommitRequest = {
      batchId: 'position-batch',
      accountId: 7,
      snapshotDate: '2026-07-13',
      positions: [{ symbol: '600519', name: '贵州茅台', quantity: 100, avgCost: 1500 }],
    };

    const result = await portfolioApi.commitPositionImages(request);

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/imports/images/positions/commit', {
      batch_id: 'position-batch',
      account_id: 7,
      snapshot_date: '2026-07-13',
      positions: [{ symbol: '600519', name: '贵州茅台', quantity: 100, avg_cost: 1500 }],
    });
    expect(result.insertedCount).toBe(1);
  });

  it('posts repeated files and preserves nullable trade time in a trade parse response', async () => {
    post.mockResolvedValueOnce({
      data: {
        batch_id: 'trade-batch',
        account_id: 7,
        default_trade_date: '2026-07-13',
        files: [{ index: 0, filename: 'trades.png', status: 'success', record_count: 2, error: null }],
        trades: [
          {
            source_refs: [{ file_index: 0, row_index: 0 }],
            trade_date: '2026-07-13',
            trade_time: '09:30:05',
            symbol: '600519',
            name: '贵州茅台',
            side: 'buy',
            quantity: 10,
            price: 1500,
            fee: 0,
            tax: 0,
            trade_uid: null,
            confidence: 'high',
            occurrence_index: 1,
            fingerprint: 'fingerprint-1',
            dedup_hash: null,
            status: 'ready',
            issues: [],
          },
          {
            source_refs: [{ file_index: 0, row_index: 1 }],
            trade_date: '2026-07-13',
            trade_time: null,
            symbol: '000001',
            name: '平安银行',
            side: 'sell',
            quantity: 20,
            price: 12,
            fee: 0,
            tax: 0,
            trade_uid: null,
            confidence: 'medium',
            occurrence_index: 1,
            fingerprint: 'fingerprint-2',
            dedup_hash: null,
            status: 'ready',
            issues: ['fees_defaulted_to_zero'],
          },
        ],
      },
    });
    const files = [new File(['trades'], 'trades.png', { type: 'image/png' })];

    const result = await portfolioApi.parseTradeImages(7, '2026-07-13', files);

    const [, body] = post.mock.calls[0];
    expect((body as FormData).getAll('files')).toEqual(files);
    expect((body as FormData).get('default_trade_date')).toBe('2026-07-13');
    expect(result.trades.map((trade) => trade.tradeTime)).toEqual(['09:30:05', null]);
    expect(result.trades[0].occurrenceIndex).toBe(1);
  });

  it('commits reviewed trades as snake_case JSON', async () => {
    post.mockResolvedValueOnce({
      data: { record_count: 1, inserted_count: 1, duplicate_count: 0, failed_count: 0, errors: [] },
    });
    const request: TradeImageCommitRequest = {
      batchId: 'trade-batch',
      accountId: 7,
      trades: [{
        tradeDate: '2026-07-13',
        tradeTime: null,
        symbol: '600519',
        name: '贵州茅台',
        side: 'buy',
        quantity: 10,
        price: 1500,
        fee: 0,
        tax: 0,
        tradeUid: null,
        occurrenceIndex: 1,
      }],
    };

    await portfolioApi.commitTradeImages(request);

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/imports/images/trades/commit', {
      batch_id: 'trade-batch',
      account_id: 7,
      trades: [{
        trade_date: '2026-07-13',
        trade_time: null,
        symbol: '600519',
        name: '贵州茅台',
        side: 'buy',
        quantity: 10,
        price: 1500,
        fee: 0,
        tax: 0,
        trade_uid: null,
        occurrence_index: 1,
      }],
    });
  });
});
