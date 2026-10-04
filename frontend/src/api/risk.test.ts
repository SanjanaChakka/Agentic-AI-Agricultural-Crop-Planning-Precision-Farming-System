import { describe, expect, it } from 'vitest';

import { containsDiagnosisLanguage, humanise, safeStatement } from '../api/risk';

/**
 * The risk surface must never put a diagnostic claim in front of a farmer.
 *
 * These guards are the last line of defence: even if the backend regressed and
 * started returning "disease confirmed", the UI restates the finding as an
 * environmental observation instead of rendering it.
 */
describe('containsDiagnosisLanguage', () => {
  it('detects a direct confirmation claim', () => {
    expect(containsDiagnosisLanguage('Bacterial blight is confirmed')).toBe(true);
  });

  it('detects a diagnosis claim', () => {
    expect(containsDiagnosisLanguage('Diagnosed with leaf blight')).toBe(true);
  });

  it('detects a disease-present claim', () => {
    expect(containsDiagnosisLanguage('disease present on lower leaves')).toBe(true);
  });

  it('detects an identification claim', () => {
    expect(containsDiagnosisLanguage('identified as powdery mildew')).toBe(true);
  });

  it('accepts the approved favourable-environment wording', () => {
    expect(
      containsDiagnosisLanguage(
        'Environmental conditions favourable for water stress: measured soil moisture 13% VWC is at or below the critical threshold.',
      ),
    ).toBe(false);
  });

  it('accepts ordinary agronomic language that merely mentions inspection', () => {
    expect(
      containsDiagnosisLanguage('Scout the canopy and send a sample to a plant clinic for confirmation.'),
    ).toBe(false);
  });
});

describe('safeStatement', () => {
  it('passes compliant wording through verbatim', () => {
    const statement = 'Environmental conditions favourable for heat stress: forecast maximum 41 deg C.';

    expect(safeStatement({ risk_type: 'heat_stress', statement })).toBe(statement);
  });

  it('restates a diagnosis claim instead of rendering it', () => {
    const result = safeStatement({
      risk_type: 'water_stress',
      statement: 'Bacterial blight is confirmed on the lower leaves.',
    });

    expect(result).not.toMatch(/confirmed/i);
    expect(result).toMatch(/Environmental conditions favourable for/i);
    expect(result).toMatch(/does not diagnose/i);
  });

  it('always frames a restatement as an environmental observation', () => {
    const result = safeStatement({
      risk_type: 'disease_favourable_environment',
      statement: 'Diagnosed with fungal leaf spot.',
    });

    expect(result.startsWith('Environmental conditions favourable for')).toBe(true);
  });
});

describe('humanise', () => {
  it('turns an enum token into readable text', () => {
    expect(humanise('water_stress')).toBe('Water stress');
  });

  it('never returns an empty label', () => {
    expect(humanise('')).toBe('this condition');
    expect(humanise('___')).toBe('this condition');
  });
});