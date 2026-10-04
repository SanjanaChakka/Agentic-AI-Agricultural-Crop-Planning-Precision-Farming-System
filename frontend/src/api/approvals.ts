import { apiClient } from './client';
import type { Approval, ApprovalDecision, SafetyContract } from './types';

export const listApprovals = async (params: {
  fieldId?: number;
  approvalStatus?: string;
  limit?: number;
} = {}): Promise<Approval[]> => {
  const { data } = await apiClient.get<Approval[]>('/approvals', {
    params: {
      field_id: params.fieldId,
      approval_status: params.approvalStatus,
      limit: params.limit ?? 50,
    },
  });
  return data;
};

export const listPendingApprovals = async (limit = 50): Promise<Approval[]> => {
  const { data } = await apiClient.get<Approval[]>('/approvals/pending', {
    params: { limit },
  });
  return data;
};

export const getApproval = async (approvalId: number): Promise<Approval> => {
  const { data } = await apiClient.get<Approval>(`/approvals/${approvalId}`);
  return data;
};

/** What approval does and - critically - does not do. */
export const getSafetyContract = async (): Promise<SafetyContract> => {
  const { data } = await apiClient.get<SafetyContract>('/approvals/safety-contract');
  return data;
};

/** Record a human decision. Approving authorises the plan only - never hardware. */
export const decideApproval = async (
  approvalId: number,
  decision: ApprovalDecision,
): Promise<Approval> => {
  const { data } = await apiClient.post<Approval>(
    `/approvals/${approvalId}/decision`,
    decision,
  );
  return data;
};