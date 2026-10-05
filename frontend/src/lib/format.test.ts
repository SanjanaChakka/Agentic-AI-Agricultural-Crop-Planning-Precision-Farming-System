import { describe, expect, it } from 'vitest';

import {
  formatBytes,
  formatDate,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelative,
  humaniseToken,
  optionLabel,
} from '../lib/format';

/**
 * Formatting helpers decide what an operator reads as "no value".
 *
 * The important property is that an absent measurement renders as a dash and
 * never as a plausible-looking zero: a "0 mm rainfall" that is really "no data"
 * would change the irrigation decision.
 */
describe('formatNumber', () => {
  it('renders a dash for a missing value rather than a zero', () => {
    expect(formatNumber(null)).toBe('-');
    expect(formatNumber(undefined)).toBe('-');
    expect(formatNumber(Number.NaN)).toBe('-');
  });

  it('never renders a missing value as 0', () => {
    expect(formatNumber(null)).not.toBe('0');
  });

  it('renders a real zero as zero', () => {
    expect(formatNumber(0)).toBe('0');
  });

  it('respects the requested precision', () => {
    expect(formatNumber(12.345, 2)).toBe('12.35');
    expect(formatNumber(12.345, 0)).toBe('12');
  });
});

describe('formatPercent', () => {
  it('renders a dash for a missing value', () => {
    expect(formatPercent(null)).toBe('-');
    expect(formatPercent(undefined)).toBe('-');
  });

  it('appends a percent sign to a real value', () => {
    expect(formatPercent(78.4)).toBe('78%');
  });
});

describe('formatBytes', () => {
  it('renders a dash for a missing or empty size', () => {
    expect(formatBytes(null)).toBe('-');
    expect(formatBytes(0)).toBe('-');
  });

  it('scales to the nearest unit', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(26_752)).toBe('26.1 KB');
  });
});

describe('formatDuration', () => {
  it('renders a dash for a missing duration', () => {
    expect(formatDuration(null)).toBe('-');
  });

  it('uses milliseconds below one second', () => {
    expect(formatDuration(450)).toBe('450 ms');
  });

  it('uses seconds below one minute', () => {
    expect(formatDuration(1808)).toBe('1.81 s');
  });

  it('uses minutes above one minute', () => {
    expect(formatDuration(125_000)).toBe('2m 5s');
  });
});

describe('date helpers', () => {
  it('render a dash for a missing or unparseable timestamp', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate('')).toBe('-');
    expect(formatDate('not-a-date')).toBe('-');
  });

  it('render a dash for a missing relative time', () => {
    expect(formatRelative(undefined)).toBe('-');
  });

  it('format a real ISO timestamp', () => {
    expect(formatDate('2026-10-04T09:30:00Z')).toMatch(/\d{2} \w{3} \d{4}/);
  });
});

describe('humaniseToken', () => {
  it('turns an enum token into readable text', () => {
    expect(humaniseToken('suitable_with_conditions')).toBe('Suitable with conditions');
  });

  it('returns the fallback for an empty value', () => {
    expect(humaniseToken(null)).toBe('-');
    expect(humaniseToken('', 'Unknown')).toBe('Unknown');
  });
});

describe('optionLabel', () => {
  const map = new Map([[1, 'North Plot'], [2, 'South Plot']]);

  it('resolves a known id', () => {
    expect(optionLabel(1, map)).toBe('North Plot');
  });

  it('falls back to the id when the name is unknown', () => {
    expect(optionLabel(99, map)).toBe('#99');
  });

  it('uses the fallback for a null id', () => {
    expect(optionLabel(null, map)).toBe('Unknown field');
  });
});