import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { insightsApi } from "@/services/api";

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
  generated_at: string;
}

export function useInsights() {
  return useQuery<InsightsData>({
    queryKey: ["insights"],
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
