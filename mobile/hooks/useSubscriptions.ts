import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { subscriptionsApi } from "@/services/api";

export interface Subscription {
  id: number;
  merchant_name: string;
  display_name: string | null;
  amount: number;
  frequency: string;
  category: string | null;
  last_charge_date: string | null;
  next_charge_date: string | null;
  confidence: number;
  status: string;
  cancel_url: string | null;
  monthly_cost: number;
}

export function useSubscriptions() {
  return useQuery<Subscription[]>({
    queryKey: ["subscriptions"],
    queryFn: async () => {
      const res = await subscriptionsApi.list("active");
      return res.data;
    },
  });
}

export function useDismiss() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => subscriptionsApi.dismiss(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
  });
}

export function useRestore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => subscriptionsApi.restore(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
  });
}
