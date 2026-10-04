import { apiClient } from './client';
import type { RiskFinding, RiskScanResponse } from './types';
import { extractApiErrorMessage } from './client';

/**
 * Wording contract for the risk surface.
 *
 * The backend guarantees findings are phrased as "Environmental conditions
 * favourable for X" and never asserts a diagnosis. This guard keeps a hostile
 * or regressed payload from ever putting diagnosis language on screen.
 */
const FORBIDDEN_RISK_TERMS = [
  'confirmed',
  'diagnos',
  'diagnosed',
  'diagnosis',
  'positive for',
  'identified as',
  'detected disease',
  'disease present',
] as const;

/** True when the text asserts a diagnosis. */
export function containsDiagnosisLanguage(text: string): boolean {
  const lowered = text.toLowerCase();
  return FORBIDDEN_RISK_TERMS.some((term) => lowered.includes(term));
}

/**
 * Render a finding statement safely: verbatim when the backend wording rule
 * holds, otherwise a neutral, explicitly non-diagnostic restatement.
 */
export function safeStatement(finding: Pick<RiskFinding, 'risk_type' | 'statement'>): string {
  if (containsDiagnosisLanguage(finding.statement)) {
    return `Environmental conditions favourable for ${humanise(finding.risk_type)} (environmental observation only - this system does not diagnose).`;
  }
  return finding.statement;
}

/** `water_stress` -> `water stress`. */
export function humanise(value: string): string {
  const cleaned = value.replace(/[_-]+/g, ' ').trim();
  if (!cleaned) return 'this condition';
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export const scanFieldRisk = async (fieldId: number, crop?: string): Promise<RiskScanResponse> => {
  try {
    const { data } = await apiClient.get<RiskScanResponse>(`/risk/fields/${fieldId}`, {
      params: crop ? { crop } : undefined,
    });
    return data;
  } catch (error) {
    throw new Error(extractApiErrorMessage(error));
  }
};

export const getRiskHistory = async (fieldId: number, limit = 20): Promise<RiskFinding[]> => {
  const { data } = await apiClient.get<RiskFinding[]>(`/risk/fields/${fieldId}/history`, {
    params: { limit },
  });
  return data;
};

/** The non-diagnostic disclaimer enforced by the system, plus its wording rule. */
export const getRiskDisclaimer = async (): Promise<{ disclaimer: string; wording_rule: string }> => {
  const { data } = await apiClient.get<{ disclaimer: string; wording_rule: string }>(
    '/risk/disclaimer',
  );
  return data;
};