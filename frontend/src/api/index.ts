/**
 * Barrel for the API layer.
 *
 * Importing from `../api` keeps components free of transport details and makes
 * `vi.mock('../api')` a single seam in tests.
 */
export * from './client';
export * from './types';
export * from './health';

export * as farmsApi from './farms';
export * as soilApi from './soil';
export * as weatherApi from './weather';
export * as suitabilityApi from './suitability';
export * as sensorsApi from './sensors';
export * as irrigationApi from './irrigation';
export * as riskApi from './risk';
export * as mlApi from './ml';
export * as workflowApi from './workflow';
export * as approvalsApi from './approvals';
export * as activitiesApi from './activities';