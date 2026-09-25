import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { subscriptionsApi } from "@/services/api";
import { useAuthStore } from "@/store/auth";

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

function useSubscriptionList(status: "active" | "dismissed" | "ended") {
  const token = useAuthStore((s) => s.token);
  return useQuery<Subscription[]>({
    queryKey: ["subscriptions", status],
    enabled: !!token, // don't fire before the saved login has been read from secure storage
    queryFn: async () => {
      const res = await subscriptionsApi.list(status);
      return res.data;
    },
  });
}

export const useSubscriptions = () => useSubscriptionList("active");
export const useDismissedSubscriptions = () => useSubscriptionList("dismissed");
/** Subscriptions whose charges stopped (probably cancelled). */
export const useEndedSubscriptions = () => useSubscriptionList("ended");

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
