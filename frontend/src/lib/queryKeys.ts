/**
 * Centralised react-query keys.
 *
 * Approving a workflow run mutates runs, approvals, activities, alerts and the
 * dashboard, so `invalidateAfterApproval` clears the whole set in one place.
 */
export const queryKeys = {
  health: () => ['health'] as const,
  dashboard: () => ['dashboard'] as const,

  farms: () => ['farms'] as const,
  farm: (farmId: number) => ['farms', farmId] as const,
  farmSummary: (farmId: number) => ['farms', farmId, 'summary'] as const,

  fields: (farmId?: number) => ['fields', farmId ?? 'all'] as const,
  field: (fieldId: number) => ['fields', 'detail', fieldId] as const,
  fieldCounts: (farmId?: number) => ['fields', 'counts', farmId ?? 'all'] as const,

  alertsOpen: (farmId?: number) => ['alerts', 'open', farmId ?? 'all'] as const,
  alerts: (params: Record<string, unknown>) => ['alerts', 'list', params] as const,

  soilLatest: (fieldId: number) => ['soil', fieldId, 'latest'] as const,
  soilObservations: (fieldId: number) => ['soil', fieldId, 'observations'] as const,
  soilThresholds: () => ['soil', 'thresholds'] as const,

  weather: (fieldId: number, days: number) => ['weather', fieldId, days] as const,
  weatherEvidence: (fieldId: number) => ['weather', fieldId, 'evidence'] as const,

  crops: () => ['suitability', 'crops'] as const,
  suitabilityHistory: (fieldId: number) => ['suitability', fieldId, 'history'] as const,

  sensorsLatest: (fieldId: number) => ['sensors', fieldId, 'latest'] as const,
  sensorsTrend: (fieldId: number, hours: number) => ['sensors', fieldId, 'trend', hours] as const,
  sensorsQuality: (fieldId: number) => ['sensors', fieldId, 'quality'] as const,

  irrigationHistory: (fieldId: number) => ['irrigation', fieldId, 'history'] as const,

  risk: (fieldId: number, crop?: string) => ['risk', fieldId, crop ?? 'default'] as const,
  riskDisclaimer: () => ['risk', 'disclaimer'] as const,

  mlPredictions: (fieldId: number) => ['ml', fieldId, 'predictions'] as const,
  mlStatus: () => ['ml', 'status'] as const,

  runs: (fieldId?: number) => ['runs', fieldId ?? 'all'] as const,
  run: (runId: number) => ['runs', 'detail', runId] as const,
  runSummary: (runId: number) => ['runs', 'summary', runId] as const,
  runTraces: (runId: number) => ['runs', 'traces', runId] as const,
  latestRun: (fieldId: number) => ['runs', 'latest', fieldId] as const,

  approvals: (fieldId?: number) => ['approvals', fieldId ?? 'all'] as const,
  pendingApprovals: () => ['approvals', 'pending'] as const,
  safetyContract: () => ['approvals', 'safety-contract'] as const,

  activities: (fieldId?: number, status?: string) =>
    ['activities', fieldId ?? 'all', status ?? 'all'] as const,

  reports: (fieldId?: number) => ['reports', fieldId ?? 'all'] as const,

  agents: () => ['agents'] as const,
};

/** Every key a human approval decision can invalidate. */
export const approvalInvalidationKeys = [
  queryKeys.dashboard(),
  queryKeys.pendingApprovals(),
  queryKeys.safetyContract(),
  queryKeys.alertsOpen(),
  ['approvals'],
  ['activities'],
  ['runs'],
  ['dashboard'],
] as const;