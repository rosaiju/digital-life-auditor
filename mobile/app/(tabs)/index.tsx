import { useCallback, useState } from "react";
import {
  View,
  Text,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
} from "react-native";
import { useRouter } from "expo-router";
import { useSubscriptions, useDismiss } from "@/hooks/useSubscriptions";
import { plaidApi } from "@/services/api";
import { SummaryBanner } from "@/components/SummaryBanner";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { EmptyState } from "@/components/EmptyState";
import { errorMessage } from "@/utils/alerts";

export default function Dashboard() {
  const router = useRouter();
  const { data: subscriptions, isLoading, error, refetch } = useSubscriptions();
  const dismiss = useDismiss();
  const [refreshing, setRefreshing] = useState(false);

  // Pull-to-refresh asks the bank for new transactions first, then reloads the list.
  // A 404 just means no bank is connected yet, which is fine.
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await plaidApi.sync();
    } catch {
      // ignore: the list reload below still shows whatever we have
    }
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  const monthlyTotal = subscriptions?.reduce((sum, s) => sum + s.monthly_cost, 0) ?? 0;

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
          <SummaryBanner
            monthlyTotal={monthlyTotal}
            count={subscriptions?.length ?? 0}
          />
        }
        ListEmptyComponent={
          error ? (
            <EmptyState
              title="Couldn't load subscriptions"
              subtitle={errorMessage(error)}
              actionLabel="Try again"
              onAction={() => refetch()}
            />
          ) : !isLoading ? (
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
            onDismiss={() => dismiss.mutate(item.id)}
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
});
