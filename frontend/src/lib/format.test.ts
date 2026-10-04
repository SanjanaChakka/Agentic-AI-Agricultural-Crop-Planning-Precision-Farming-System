import { describe, expect, it } from 'vitest';
import { formatBytes, formatNumber, formatPercent } from './format';

describe('formatNumber', () => {
  it('renders nullish values as a dash', () => {
    expect(formatNumber(null)).toBe('-');
    expect(formatNumber(undefined)).toBe('-');
    expect(formatNumber(NaN)).toBe('-');
  });

  it('keeps configured precision', () => {
    expect(formatNumber(1042.56, 1)).toBe('1,042.6');
    expect(formatNumber(0.5, 2)).toBe('0.5');
  });
});

describe('formatPercent', () => {
  it('appends a percent sign', () => {
    expect(formatPercent(68.455, 1)).toBe('68.5%');
  });

  it('renders nullish values as a dash', () => {
    expect(formatPercent(null)).toBe('-');
  });
});

describe('formatBytes', () => {
  it('scales bytes into human units', () => {
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(0)).toBe('-');
  });
});
