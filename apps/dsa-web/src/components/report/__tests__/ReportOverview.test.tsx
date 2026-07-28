import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportOverview } from '../ReportOverview';

const baseMeta = {
  queryId: 'q-1',
  stockCode: '600519',
  stockName: '贵州茅台',
  reportType: 'detailed' as const,
  reportLanguage: 'zh' as const,
  createdAt: '2026-03-21T08:00:00Z',
};

const baseSummary = {
  analysisSummary: '趋势维持强势',
  operationAdvice: '继续观察买点',
  trendPrediction: '短线震荡偏强',
  sentimentScore: 78,
};

describe('ReportOverview', () => {
  it('renders the effective strategy and source in report metadata', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          strategyExecution: {
            schemaVersion: 1,
            status: 'normal',
            source: 'request',
            requested: [{ id: 'box_oscillation', displayName: '箱体震荡', status: 'selected' }],
            effective: [{ id: 'box_oscillation', displayName: '箱体震荡', status: 'selected' }],
            rejected: [],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByText(/分析策略: 箱体震荡/)).toBeVisible();
    expect(screen.getAllByText(/本次指定/).length).toBeGreaterThan(0);
  });

  it('shows additional strategies and fallback details without overflowing the header', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          strategyExecution: {
            schemaVersion: 1,
            status: 'fallback',
            source: 'fallback',
            requested: [{ id: 'removed_skill', displayName: '已删除策略', status: 'selected' }],
            effective: [
              { id: 'bull_trend', displayName: '趋势策略', status: 'selected' },
              { id: 'box_oscillation', displayName: '箱体震荡', status: 'selected' },
            ],
            rejected: [{ id: 'removed_skill', reason: 'unavailable' }],
            message: '请求策略不可用，已使用系统默认策略。',
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByText(/分析策略: 趋势策略 \+1/)).toBeVisible();
    expect(screen.getAllByText('系统回退').length).toBeGreaterThan(0);
    expect(screen.getByRole('status')).toHaveTextContent('系统回退');
  });

  it('renders the persisted auto-match basis and complete-bar cutoff', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          strategyExecution: {
            schemaVersion: 1,
            status: 'normal',
            source: 'auto',
            requested: [],
            effective: [{ id: 'volume_breakout', displayName: '放量突破', status: 'selected' }],
            rejected: [],
            selectionContext: {
              mode: 'auto_match',
              status: 'matched',
              asOf: '2026-07-27',
              matchedPatterns: ['放量突破20日高点'],
              candidates: [{ skillId: 'volume_breakout', mode: 'analysis', matchedPatterns: ['放量突破20日高点'] }],
              selectedSkillId: 'volume_breakout',
              fallbackReason: null,
            },
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getAllByText(/自动匹配/).length).toBeGreaterThan(0);
    expect(screen.getByText('完整日线截止: 2026-07-27')).toBeInTheDocument();
    expect(screen.getByText('匹配依据: 放量突破20日高点')).toBeInTheDocument();
  });

  it('marks legacy reports as having no recorded strategy metadata', () => {
    render(<ReportOverview meta={baseMeta} summary={baseSummary} />);

    expect(screen.getByText('分析策略: 未记录')).toBeVisible();
    expect(screen.getByTitle('该报告生成时未保存策略信息')).toBeVisible();
  });

  it('renders final market phase and partial-bar labels from report metadata', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          marketPhaseSummary: {
            market: 'cn',
            phase: 'intraday',
            marketLocalTime: '2026-03-21T10:30:00+08:00',
            sessionDate: '2026-03-21',
            effectiveDailyBarDate: '2026-03-20',
            isTradingDay: true,
            isMarketOpenNow: true,
            isPartialBar: true,
            minutesToOpen: null,
            minutesToClose: 150,
            triggerSource: 'api',
            analysisIntent: 'auto',
            warnings: [],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByLabelText('市场阶段: CN · 盘中')).toBeInTheDocument();
    expect(screen.getByText('市场阶段: CN · 盘中')).toBeVisible();
    expect(screen.getByLabelText('日线未完成')).toBeInTheDocument();
  });

  it('renders English final market phase and partial-bar labels', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          reportLanguage: 'en',
          marketPhaseSummary: {
            market: 'us',
            phase: 'postmarket',
            marketLocalTime: '2026-03-21T16:30:00-04:00',
            sessionDate: '2026-03-21',
            effectiveDailyBarDate: '2026-03-21',
            isTradingDay: true,
            isMarketOpenNow: false,
            isPartialBar: true,
            minutesToOpen: null,
            minutesToClose: null,
            triggerSource: 'api',
            analysisIntent: 'auto',
            warnings: [],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByLabelText('Market phase: US · Post-market')).toBeInTheDocument();
    expect(screen.getByLabelText('Partial bar')).toBeInTheDocument();
  });

  it('renders unknown final phase without partial-bar label', () => {
    render(
      <ReportOverview
        meta={{
          ...baseMeta,
          marketPhaseSummary: {
            market: null,
            phase: 'unknown',
            marketLocalTime: null,
            sessionDate: null,
            effectiveDailyBarDate: null,
            isTradingDay: null,
            isMarketOpenNow: null,
            isPartialBar: false,
            minutesToOpen: null,
            minutesToClose: null,
            triggerSource: 'api',
            analysisIntent: 'auto',
            warnings: ['calendar_unavailable'],
          },
        }}
        summary={baseSummary}
      />,
    );

    expect(screen.getByText('市场阶段: 阶段未知')).toBeVisible();
    expect(screen.queryByText('日线未完成')).not.toBeInTheDocument();
  });

  it('does not render a market phase placeholder for legacy reports', () => {
    render(<ReportOverview meta={baseMeta} summary={baseSummary} />);

    expect(screen.queryByText(/市场阶段/)).not.toBeInTheDocument();
    expect(screen.queryByText('日线未完成')).not.toBeInTheDocument();
  });

  it('renders related boards with leading and lagging markers', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [
            { name: ' 白酒 ', type: '行业' },
            { name: '消费', type: '概念' },
            { name: '新能源' },
          ],
          sectorRankings: {
            top: [{ name: '白酒', changePct: 2.31 }],
            bottom: [{ name: '新能源', changePct: -1.2 }],
          },
          conceptRankings: {
            top: [{ name: '消费', changePct: 4.56 }],
            bottom: [],
          },
        }}
      />,
    );

    expect(screen.getByText('关联板块')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
    expect(screen.getAllByText('领涨')).toHaveLength(2);
    expect(screen.getByText('+2.31%')).toBeInTheDocument();
    expect(screen.getByText('+4.56%')).toBeInTheDocument();
    expect(screen.getByText('领跌')).toBeInTheDocument();
    expect(screen.getByText('-1.20%')).toBeInTheDocument();
    expect(screen.queryByText('中性')).not.toBeInTheDocument();
  });

  it('does not apply industry ranking to a concept board with the same name', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [{ name: '白酒', type: '概念' }],
          sectorRankings: {
            top: [{ name: '白酒', changePct: 2.31 }],
            bottom: [],
          },
          conceptRankings: {
            top: [],
            bottom: [{ name: '白酒', changePct: -3.2 }],
          },
        }}
      />,
    );

    expect(screen.getByText('白酒')).toBeInTheDocument();
    expect(screen.getByText('关联板块')).toBeInTheDocument();
    expect(screen.getByText('领跌')).toBeInTheDocument();
    expect(screen.getByText('-3.20%')).toBeInTheDocument();
    expect(screen.queryByText('+2.31%')).not.toBeInTheDocument();
  });

  it('renders untyped boards in a single related-board row with ranking matches', () => {
    const conceptRankingBoard = '榜单样例甲';
    const fallbackConceptBoard = '未标注板块';
    const sectorRankingBoard = '榜单样例乙';

    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [
            { name: conceptRankingBoard },
            { name: fallbackConceptBoard },
            { name: sectorRankingBoard },
          ],
          sectorRankings: {
            top: [{ name: sectorRankingBoard, changePct: 1.11 }],
            bottom: [],
          },
          conceptRankings: {
            top: [{ name: conceptRankingBoard, changePct: 3.21 }],
            bottom: [],
          },
        }}
      />,
    );

    const relatedBoardsRegion = screen.getByRole('region', { name: '关联板块' });

    expect(within(relatedBoardsRegion).getByText(sectorRankingBoard)).toBeInTheDocument();
    expect(within(relatedBoardsRegion).getByText(conceptRankingBoard)).toBeInTheDocument();
    expect(within(relatedBoardsRegion).getByText(fallbackConceptBoard)).toBeInTheDocument();
    expect(within(relatedBoardsRegion).getByText('+3.21%')).toBeInTheDocument();
  });

  it('places related boards below action advice in one horizontal row', () => {
    const { container } = render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [
            { name: '白酒', type: '行业' },
            { name: '消费', type: '概念' },
            { name: '高端制造' },
            { name: '沪股通' },
          ],
        }}
      />,
    );

    const actionAdviceTitle = screen.getByText('操作建议');
    const relatedBoardsRegion = screen.getByRole('region', { name: '关联板块' });
    const boardLists = container.querySelectorAll('.home-related-board-list');

    expect(actionAdviceTitle.compareDocumentPosition(relatedBoardsRegion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('关联板块')).toBeInTheDocument();
    expect(screen.getByText('沪股通')).toBeInTheDocument();
    expect(boardLists[0]).toHaveClass(
      'flex-nowrap',
      'overflow-x-auto',
      'w-full',
      'min-w-0',
      'max-w-full',
      'touch-pan-x',
    );
  });

  it('shows board list when rankings are unavailable', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [{ name: '半导体', type: '行业' }],
        }}
      />,
    );

    expect(screen.getByText('关联板块')).toBeInTheDocument();
    expect(screen.getByText('半导体')).toBeInTheDocument();
    expect(screen.queryByText('中性')).not.toBeInTheDocument();
    expect(screen.queryByText('领涨')).not.toBeInTheDocument();
    expect(screen.queryByText('领跌')).not.toBeInTheDocument();
  });

  it('shows only the board when a matching ranking has no change percent', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [{ name: '白酒', type: '行业' }],
          sectorRankings: {
            top: [{ name: '白酒' }],
            bottom: [],
          },
        }}
      />,
    );

    expect(screen.getByText('关联板块')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
    expect(screen.queryByText('行业')).not.toBeInTheDocument();
    expect(screen.queryByText('领涨')).not.toBeInTheDocument();
    expect(screen.queryByText('领跌')).not.toBeInTheDocument();
  });

  it('hides related boards section when no boards are available', () => {
    render(<ReportOverview meta={baseMeta} summary={baseSummary} details={{ belongBoards: [] }} />);

    expect(screen.queryByText('板块联动')).not.toBeInTheDocument();
  });

  it('fails open on malformed ranking payloads', () => {
    render(
      <ReportOverview
        meta={baseMeta}
        summary={baseSummary}
        details={{
          belongBoards: [{ name: ' 白酒 ' }],
          sectorRankings: {
            top: {} as unknown as never[],
            bottom: [{ name: '白酒', changePct: '-2.5%' as unknown as number }],
          },
        }}
      />,
    );

    expect(screen.getByText('关联板块')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
    expect(screen.getByText('领跌')).toBeInTheDocument();
    expect(screen.getByText('-2.50%')).toBeInTheDocument();
  });
});
