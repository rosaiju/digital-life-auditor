import { useCallback, useState } from "react";
import {
  View,
  Text,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  StyleSheet,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useSubscriptions, useDismiss, useEndedSubscriptions } from "@/hooks/useSubscriptions";
import { usePlaidItems, needsReconnect } from "@/hooks/usePlaidItems";
import { useQueryClient } from "@tanstack/react-query";
import { plaidApi } from "@/services/api";
import { SummaryBanner } from "@/components/SummaryBanner";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { EmptyState } from "@/components/EmptyState";
import { Banner } from "@/components/Banner";
import { errorMessage, showAlert } from "@/utils/alerts";

export default function Dashboard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: subscriptions, isLoading, isPending, error, refetch } = useSubscriptions();
  const ended = useEndedSubscriptions();
  const items = usePlaidItems();
  const dismiss = useDismiss();
  const [refreshing, setRefreshing] = useState(false);
  const [syncProblem, setSyncProblem] = useState<string | null>(null);

  // Pull-to-refresh asks the bank for new transactions first, then reloads the list.
  // A 404 just means no bank is connected yet, which is fine; anything else is shown.
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    setSyncProblem(null);
    try {
      const res = await plaidApi.sync();
      const failed = res.data.failed ?? [];
      if (failed.length > 0) {
        setSyncProblem(`Couldn't sync ${failed.map((f) => f.institution_name ?? "a bank").join(", ")}.`);
      }
    } catch (e: any) {
      if (e?.response?.status !== 404) setSyncProblem(errorMessage(e));
    }
    await Promise.all([refetch(), ended.refetch(), queryClient.invalidateQueries({ queryKey: ["plaid-items"] })]);
    setRefreshing(false);
  }, [refetch, ended, queryClient]);

  const monthlyTotal = subscriptions?.reduce((sum, s) => sum + s.monthly_cost, 0) ?? 0;
  const reconnect = needsReconnect(items.data);
  const endedNames = (ended.data ?? []).map((s) => s.display_name ?? s.merchant_name);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Subscriptions</Text>
        <TouchableOpacity
          style={styles.connectBtn}
          onPress={() => router.push("/connect-bank")}
        >
          <Text style={styles.connectBtnText}>+ Bank</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={subscriptions}
        keyExtractor={(item) => String(item.id)}
        ListHeaderComponent={
          <View>
            {reconnect.map((item) => (
              <Banner
                key={item.id}
                message={`${item.institution_name ?? "A bank"} needs you to sign in again before it can sync.`}
                actionLabel="Reconnect"
                onAction={() => router.push({ pathname: "/connect-bank", params: { itemId: String(item.id) } })}
              />
            ))}
            {syncProblem && <Banner tone="error" message={syncProblem} />}
            <SummaryBanner monthlyTotal={monthlyTotal} count={subscriptions?.length ?? 0} />
          </View>
        }
        ListFooterComponent={
          endedNames.length > 0 ? (
            <Text style={styles.ended}>
              No recent charge from {endedNames.join(", ")}: probably cancelled, so not counted above.
            </Text>
          ) : null
        }
        ListEmptyComponent={
          error ? (
            <EmptyState
              title="Couldn't load subscriptions"
              subtitle={errorMessage(error)}
              actionLabel="Try again"
              onAction={() => refetch()}
            />
          ) : !isPending ? (
            <EmptyState
              title="No subscriptions found"
              subtitle="Connect a bank account to scan for recurring charges"
              actionLabel="Connect Bank"
              onAction={() => router.push("/connect-bank")}
            />
          ) : null
        }
        renderItem={({ item }) => (
          <SubscriptionCard
            subscription={item}
            onDismiss={() =>
              dismiss.mutate(item.id, { onError: (e) => showAlert("Couldn't dismiss", errorMessage(e)) })
            }
          />
        )}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing || isLoading}
            onRefresh={onRefresh}
            tintColor="#6366f1"
          />
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 8,
  },
  title: { fontSize: 24, fontWeight: "700", color: "#f8fafc" },
  connectBtn: {
    backgroundColor: "#1e293b",
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderWidth: 1,
    borderColor: "#334155",
  },
  connectBtnText: { color: "#6366f1", fontWeight: "600", fontSize: 13 },
  list: { paddingHorizontal: 16, paddingBottom: 32 },
  ended: { color: "#64748b", fontSize: 12, lineHeight: 18, textAlign: "center", marginTop: 12 },
});
