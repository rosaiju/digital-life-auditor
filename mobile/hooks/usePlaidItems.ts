import { useQuery } from "@tanstack/react-query";
import { plaidApi, PlaidItem } from "@/services/api";
import { useAuthStore } from "@/store/auth";

export function usePlaidItems() {
  const token = useAuthStore((s) => s.token);
  return useQuery<PlaidItem[]>({
    queryKey: ["plaid-items"],
    enabled: !!token,
    queryFn: async () => (await plaidApi.items()).data,
  });
}

/** Banks that need the user to sign in again. */
export function needsReconnect(items: PlaidItem[] | undefined): PlaidItem[] {
  return (items ?? []).filter((i) => i.status === "login_required");
}
