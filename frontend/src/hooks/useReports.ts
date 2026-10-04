import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createReport, deleteReport, listReports } from '../api/workflow';
import { queryKeys } from '../lib/queryKeys';

export const useReports = (fieldId?: number) =>
  useQuery({
    queryKey: queryKeys.reports(fieldId),
    queryFn: () => listReports(fieldId ? { fieldId } : {}),
  });

export const useCreateReport = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { fieldId: number; workflowRunId: number }) =>
      createReport(variables.fieldId, variables.workflowRunId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reports'] });
    },
  });
};

export const useDeleteReport = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { reportId: number }) => deleteReport(variables.reportId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reports'] });
    },
  });
};