import { describe, expect, it } from 'vitest';
import { safeSeverityLabel, safeSeverityTone } from './RiskBadge';

describe('safeSeverityLabel', () => {
  it('maps known bands to friendly labels', () => {
    expect(safeSeverityLabel('high')).toBe('High');
    expect(safeSeverityLabel('none')).toBe('None expected');
  });

  it('neutralises diagnosis-language input', () => {
    expect(safeSeverityLabel('disease confirmed')).toBe('Unrated');
    expect(safeSeverityLabel('positively identified')).toBe('Unrated');
  });

  it('falls back to Unrated for missing values', () => {
    expect(safeSeverityLabel(null)).toBe('Unrated');
    expect(safeSeverityLabel('')).toBe('Unrated');
  });
});

describe('safeSeverityTone', () => {
  it('uses danger for high', () => {
    expect(safeSeverityTone('high')).toBe('danger');
  });
});
