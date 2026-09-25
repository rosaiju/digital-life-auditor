import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { insightsApi } from "@/services/api";
import { useAuthStore } from "@/store/auth";

export interface Insight {
  type: "redundant" | "savings" | "warning" | "tip";
  title: string;
  detail: string;
  potential_savings: number;
}

export interface InsightsData {
  summary: string;
  insights: Insight[];
  category_breakdown: Record<string, number>;
  top_opportunity: string | null;
  monthly_total: number;
  yearly_total: number;
  subscription_count: number;
  /** "ai" when written by the language model, "rules" for the built-in analysis. */
  source?: "ai" | "rules";
  generated_at: string;
}

/** The API returns {message} instead of insights until some have been generated. */
export type InsightsResponse = InsightsData | { message: string };

export function hasInsights(data: InsightsResponse | undefined): data is InsightsData {
  return !!data && !("message" in data);
}

export function useInsights() {
  const token = useAuthStore((s) => s.token);
  return useQuery<InsightsResponse>({
    queryKey: ["insights"],
    enabled: !!token,
    queryFn: async () => {
      const res = await insightsApi.get();
      return res.data;
    },
    retry: false,
  });
}

export function useGenerateInsights() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => insightsApi.generate(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["insights"] }),
  });
}
