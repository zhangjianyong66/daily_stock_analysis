import React from 'react';
import { ChevronDown, Sparkles } from 'lucide-react';
import { Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import type { KlinePatternReport as KlinePatternReportType, ReportLanguage } from '../../types/analysis';

interface Props {
  report?: KlinePatternReportType | null;
  language?: ReportLanguage;
  onSelectStrategy?: (skillId: string) => void;
}

const copy = {
  zh: { eyebrow: '日线形态', title: '形态与后续策略', details: '形态明细', recommendations: '匹配策略', choose: '选择此策略', unavailable: '形态数据暂不可用', insufficient: '日线数据不足，暂不生成推荐', evidence: '证据不足' },
  en: { eyebrow: 'Daily patterns', title: 'Patterns and next strategies', details: 'Pattern details', recommendations: 'Matched strategies', choose: 'Choose strategy', unavailable: 'Pattern data unavailable', insufficient: 'Insufficient daily data; no recommendation', evidence: 'Insufficient evidence' },
  ko: { eyebrow: '일봉 패턴', title: '패턴 및 후속 전략', details: '패턴 세부정보', recommendations: '추천 전략', choose: '이 전략 선택', unavailable: '패턴 데이터를 사용할 수 없음', insufficient: '일봉 데이터 부족으로 추천하지 않음', evidence: '근거 부족' },
} as const;

export const KlinePatternReport: React.FC<Props> = ({ report, language = 'zh', onSelectStrategy }) => {
  if (!report) return null;
  const text = copy[language] || copy.zh;
  const unavailable = report.status === 'unavailable' || report.status === 'not_supported';
  const insufficient = report.status === 'insufficient_data';
  return (
    <Card variant="bordered" padding="md" className="home-panel-card" data-testid="kline-pattern-report">
      <DashboardPanelHeader eyebrow={text.eyebrow} title={text.title} className="mb-2" />
      <p className="text-sm text-foreground">{unavailable ? text.unavailable : insufficient ? text.insufficient : (report.summary || text.evidence)}</p>
      {!unavailable && !insufficient && report.patterns.length > 0 ? (
        <details className="mt-3 rounded-lg border border-subtle bg-muted/20 px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-secondary-text">
            <span>{text.details} ({report.patterns.length})</span><ChevronDown className="h-4 w-4" aria-hidden="true" />
          </summary>
          <div className="mt-2 space-y-2">
            {report.patterns.map((pattern, index) => (
              <div key={`${pattern.name}-${index}`} className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
                <span className="font-medium text-foreground">{pattern.name}</span>
                <span className="text-muted-text">{pattern.strength || ''}{pattern.description ? ` · ${pattern.description}` : ''}</span>
              </div>
            ))}
          </div>
        </details>
      ) : null}
      {report.recommendations.length > 0 ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-secondary-text"><Sparkles className="h-3.5 w-3.5" aria-hidden="true" />{text.recommendations}</div>
          {report.recommendations.map((item) => (
            <div key={item.skillId} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-subtle px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-foreground">{item.displayName}</div>
                <div className="text-xs leading-5 text-muted-text">{item.reason}</div>
              </div>
              {onSelectStrategy ? <button type="button" className="home-surface-button shrink-0 px-2.5 py-1.5 text-xs" onClick={() => onSelectStrategy(item.skillId)}>{text.choose}</button> : null}
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  );
};
