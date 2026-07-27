import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { KlinePatternReport } from '../KlinePatternReport';

describe('KlinePatternReport', () => {
  it('shows summary, collapsible details, and only changes strategy through callback', () => {
    const onSelectStrategy = vi.fn();
    render(
      <KlinePatternReport
        language="zh"
        onSelectStrategy={onSelectStrategy}
        report={{
          schemaVersion: 'kline-pattern-v1',
          status: 'ok',
          period: 'daily',
          windowDays: 60,
          patterns: [{ name: '箱体震荡', type: 'consolidation', strength: '中', description: '区间内震荡' }],
          summary: '形态识别完成：箱体震荡',
          recommendations: [{ skillId: 'box_oscillation', displayName: '箱体震荡', matchedPatterns: ['箱体震荡'], reason: '等待确认', mode: 'analysis' }],
        }}
      />,
    );
    expect(screen.getByText('形态识别完成：箱体震荡')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '选择此策略' }));
    expect(onSelectStrategy).toHaveBeenCalledWith('box_oscillation');
  });
});
