"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { examsAdminApi } from "@/lib/api";
import { questionsModuleKeys } from "./queryKeys";
import type { AdminModuleQuestion } from "./types";

function unwrapQuestionsList(data: unknown): AdminModuleQuestion[] {
  if (Array.isArray(data)) return data as AdminModuleQuestion[];
  if (data && typeof data === "object" && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: AdminModuleQuestion[] }).results;
  }
  return [];
}

/** Uses backend ordering only (see AdminQuestionViewSet.get_queryset ``order_by``). */
export function useModuleQuestionsQuery(testId: number, moduleId: number) {
  return useQuery({
    queryKey: questionsModuleKeys.list(testId, moduleId),
    queryFn: async () => unwrapQuestionsList(await examsAdminApi.getQuestions(testId, moduleId)),
    enabled: Number.isFinite(testId) && testId > 0 && Number.isFinite(moduleId) && moduleId > 0,
    staleTime: 0,
  });
}

export function useReorderModuleQuestion(testId: number, moduleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { questionId: number; action: "up" | "down" }) => {
      await examsAdminApi.reorderQuestion(testId, moduleId, args.questionId, args.action);
    },
    onSettled: async () => {
      await qc.invalidateQueries({ queryKey: questionsModuleKeys.list(testId, moduleId) });
    },
  });
}

/**
 * Atomically reorder all questions in a module via a single POST.
 * Pass the complete ordered array of question IDs — partial reorders are rejected by the server.
 *
 * This replaces the sequential `useReorderModuleQuestion` loop that was used
 * as a temporary DnD implementation. The optimistic local state update in
 * ModuleQuestionsPanel remains unchanged; only the API call changes.
 */
export function useReorderModuleQuestionsBulk(testId: number, moduleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (orderedIds: number[]) => {
      await examsAdminApi.reorderQuestionsBulk(testId, moduleId, orderedIds);
    },
    onSettled: async () => {
      await qc.invalidateQueries({ queryKey: questionsModuleKeys.list(testId, moduleId) });
    },
  });
}

/** Backend merges defaults for omitted fields (subject from module's practice test). Send `{}`. */
export function useCreateModuleQuestion(testId: number, moduleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => examsAdminApi.createQuestion(testId, moduleId, {}, false),
    onSettled: async () => {
      await qc.invalidateQueries({ queryKey: questionsModuleKeys.list(testId, moduleId) });
    },
  });
}

export function useUpdateModuleQuestion(testId: number, moduleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { questionId: number; data: Partial<AdminModuleQuestion> & Record<string, unknown> | FormData }) => {
      const isFormData = args.data instanceof FormData;
      return examsAdminApi.updateQuestion(testId, moduleId, args.questionId, args.data, isFormData) as Promise<AdminModuleQuestion>;
    },
    onSettled: async () => {
      await qc.invalidateQueries({ queryKey: questionsModuleKeys.list(testId, moduleId) });
    },
  });
}

export function useDeleteModuleQuestion(testId: number, moduleId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (questionId: number) => {
      await examsAdminApi.deleteQuestion(testId, moduleId, questionId);
    },
    onSettled: async () => {
      await qc.invalidateQueries({ queryKey: questionsModuleKeys.list(testId, moduleId) });
    },
  });
}
