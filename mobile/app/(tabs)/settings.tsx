import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { plaidApi, subscriptionsApi } from "@/services/api";
import { useDismissedSubscriptions } from "@/hooks/useSubscriptions";
import { usePlaidItems } from "@/hooks/usePlaidItems";
import { timeAgo } from "@/utils/dates";
import { confirm, showAlert, errorMessage } from "@/utils/alerts";

export default function Settings() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const logout = useAuthStore((s) => s.logout);
  const [syncing, setSyncing] = useState(false);

  const items = usePlaidItems();
  const dismissed = useDismissedSubscriptions();

  const disconnect = useMutation({
    mutationFn: (id: number) => plaidApi.disconnect(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plaid-items"] }),
    onError: (e) => showAlert("Couldn't disconnect", errorMessage(e)),
  });

  const restoreAll = useMutation({
    mutationFn: async () => {
      await Promise.all((dismissed.data ?? []).map((s) => subscriptionsApi.restore(s.id)));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
    onError: (e) => showAlert("Couldn't restore", errorMessage(e)),
  });

  async function handleSync() {
    setSyncing(true);
    try {
      const res = await plaidApi.sync();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
        queryClient.invalidateQueries({ queryKey: ["plaid-items"] }),
      ]);
      const added = res.data.transactions_added ?? 0;
      const failed = res.data.failed ?? [];
      if (failed.length > 0) {
        showAlert(
          "Some banks didn't sync",
          failed.map((f) => `${f.institution_name ?? "A bank"}: ${f.error}`).join("\n")
        );
      } else {
        showAlert("Synced", added ? `${added} new transaction${added === 1 ? "" : "s"} found.` : "Everything is up to date.");
      }
    } catch (e: any) {
      await queryClient.invalidateQueries({ queryKey: ["plaid-items"] }); // the failure is recorded per bank
      showAlert("Sync failed", errorMessage(e, "No connected accounts"));
    } finally {
      setSyncing(false);
    }
  }

  function handleDisconnect(id: number, name: string | null) {
    confirm(
      {
        title: "Disconnect bank",
        message: `Stop tracking ${name ?? "this bank"}? Detected subscriptions stay until you dismiss them.`,
        confirmLabel: "Disconnect",
        destructive: true,
      },
      () => disconnect.mutate(id)
    );
  }

  function handleLogout() {
    confirm(
      { title: "Sign Out", message: "Are you sure you want to sign out?", confirmLabel: "Sign Out", destructive: true },
      logout
    );
  }

  const dismissedCount = dismissed.data?.length ?? 0;

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.inner}>
        <Text style={styles.title}>Settings</Text>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>BANK ACCOUNTS</Text>

          {items.isLoading && <ActivityIndicator color="#6366f1" style={{ marginVertical: 12 }} />}
          {items.isError && (
            <Text style={styles.problem}>Couldn't load your banks: {errorMessage(items.error)}</Text>
          )}
          {items.data?.map((item) => {
            const broken = item.status !== "ok";
            return (
              <View key={item.id} style={styles.row}>
                <Ionicons name="business-outline" size={20} color={broken ? "#f59e0b" : "#22c55e"} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.bankName}>{item.institution_name ?? "Connected bank"}</Text>
                  <Text style={[styles.bankStatus, broken && styles.bankStatusBroken]}>
                    {item.status === "login_required"
                      ? "Sign-in needed"
                      : item.status === "error"
                      ? "Last sync failed"
                      : item.last_synced_at
                      ? `Synced ${timeAgo(item.last_synced_at)}`
                      : "Not synced yet"}
                  </Text>
                </View>
                {item.status === "login_required" && (
                  <TouchableOpacity
                    onPress={() => router.push({ pathname: "/connect-bank", params: { itemId: String(item.id) } })}
                    hitSlop={8}
                  >
                    <Text style={styles.reconnect}>Reconnect</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => handleDisconnect(item.id, item.institution_name)} hitSlop={8}>
                  <Text style={styles.disconnect}>Disconnect</Text>
                </TouchableOpacity>
              </View>
            );
          })}

          <TouchableOpacity style={styles.row} onPress={() => router.push("/connect-bank")}>
            <Ionicons name="link-outline" size={20} color="#6366f1" />
            <Text style={styles.rowText}>Connect Bank Account</Text>
            <Ionicons name="chevron-forward" size={16} color="#475569" />
          </TouchableOpacity>

          <TouchableOpacity style={styles.row} onPress={handleSync} disabled={syncing}>
            <Ionicons name="refresh-outline" size={20} color="#6366f1" />
            <Text style={styles.rowText}>Sync Transactions Now</Text>
            {syncing ? (
              <ActivityIndicator color="#6366f1" size="small" />
            ) : (
              <Ionicons name="chevron-forward" size={16} color="#475569" />
            )}
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>SUBSCRIPTIONS</Text>
          <TouchableOpacity
            style={[styles.row, dismissedCount === 0 && styles.rowDisabled]}
            onPress={() => restoreAll.mutate()}
            disabled={dismissedCount === 0 || restoreAll.isPending}
          >
            <Ionicons name="eye-outline" size={20} color="#6366f1" />
            <Text style={styles.rowText}>Restore dismissed</Text>
            <Text style={styles.rowValue}>{dismissedCount}</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>ACCOUNT</Text>
          <TouchableOpacity style={styles.row} onPress={() => router.push("/change-password")}>
            <Ionicons name="key-outline" size={20} color="#6366f1" />
            <Text style={styles.rowText}>Change password</Text>
            <Ionicons name="chevron-forward" size={16} color="#475569" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.row} onPress={() => router.push("/delete-account")}>
            <Ionicons name="trash-outline" size={20} color="#ef4444" />
            <Text style={[styles.rowText, { color: "#f87171" }]}>Delete account</Text>
            <Ionicons name="chevron-forward" size={16} color="#475569" />
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>APP</Text>
          <View style={styles.row}>
            <Ionicons name="information-circle-outline" size={20} color="#64748b" />
            <Text style={styles.rowText}>Version</Text>
            <Text style={styles.rowValue}>1.0.0</Text>
          </View>
        </View>

        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={18} color="#ef4444" />
          <Text style={styles.logoutText}>Sign Out</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  inner: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: "700", color: "#f8fafc", marginBottom: 28 },
  section: { marginBottom: 28 },
  sectionLabel: {
    color: "#475569",
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 1,
    marginBottom: 10,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1e293b",
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    gap: 12,
    borderWidth: 1,
    borderColor: "#334155",
  },
  rowDisabled: { opacity: 0.5 },
  rowText: { flex: 1, color: "#f8fafc", fontSize: 15 },
  rowValue: { color: "#64748b", fontSize: 14 },
  disconnect: { color: "#ef4444", fontSize: 13, fontWeight: "600" },
  reconnect: { color: "#f59e0b", fontSize: 13, fontWeight: "700" },
  bankName: { color: "#f8fafc", fontSize: 15 },
  bankStatus: { color: "#64748b", fontSize: 12, marginTop: 2 },
  bankStatusBroken: { color: "#f59e0b" },
  problem: { color: "#f87171", fontSize: 13, marginBottom: 10 },
  logoutBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: "#450a0a",
    backgroundColor: "#1c0808",
  },
  logoutText: { color: "#ef4444", fontWeight: "600", fontSize: 15 },
});
