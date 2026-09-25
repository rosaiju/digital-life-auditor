import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { create, open, LinkSuccess, LinkExit } from "react-native-plaid-link-sdk";
import { useQueryClient } from "@tanstack/react-query";
import { plaidApi } from "@/services/api";
import { showAlert, errorMessage } from "@/utils/alerts";
import { Ionicons } from "@expo/vector-icons";

export default function ConnectBank() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(false);
  // Present when the user is fixing a bank whose login expired (Link "update mode").
  const { itemId } = useLocalSearchParams<{ itemId?: string }>();
  const reconnectId = itemId ? Number(itemId) : null;

  async function refreshAfterLink() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
      queryClient.invalidateQueries({ queryKey: ["plaid-items"] }),
    ]);
  }

  async function onPlaidSuccess(success: LinkSuccess) {
    setLoading(true);
    try {
      if (reconnectId !== null) {
        await plaidApi.reconnected(reconnectId);
        await refreshAfterLink();
        showAlert("Reconnected", "Your bank is syncing again.");
        router.replace("/(tabs)");
        return;
      }
      const res = await plaidApi.exchange(success.publicToken, success.metadata.institution?.name);
      await refreshAfterLink();
      const found = res.data.subscriptions_found ?? 0;
      showAlert(
        "Connected!",
        res.data.transactions_added
          ? `Scanned your transactions and found ${found} subscription${found === 1 ? "" : "s"}.`
          : "Your bank is connected. Transactions can take a minute to become available; pull down on the Subscriptions tab to refresh."
      );
      router.replace("/(tabs)");
    } catch (e) {
      showAlert("Couldn't connect", errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  function onPlaidExit(exit: LinkExit) {
    if (exit.error) {
      showAlert("Connection cancelled", exit.error.displayMessage ?? "Try again");
    }
  }

  async function handleConnect() {
    setLoading(true);
    try {
      const res = reconnectId !== null ? await plaidApi.reconnectLinkToken(reconnectId) : await plaidApi.getLinkToken();
      create({ token: res.data.link_token });
      await open({ onSuccess: onPlaidSuccess, onExit: onPlaidExit });
    } catch (e) {
      showAlert("Couldn't start bank connection", errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <TouchableOpacity style={styles.back} onPress={() => router.back()} accessibilityLabel="Go back">
          <Ionicons name="arrow-back" size={22} color="#94a3b8" />
        </TouchableOpacity>

        <Text style={styles.title}>{reconnectId !== null ? "Reconnect Your Bank" : "Connect Your Bank"}</Text>
        <Text style={styles.subtitle}>
          We use Plaid to securely connect to your bank. Your bank login is never shared with us, we only read
          transaction history, and the access token is encrypted on our server.
        </Text>

        <View style={styles.featureList}>
          {[
            "Read-only access: we can't move money",
            "Powered by Plaid, used by thousands of apps",
            "Disconnect any time in Settings",
          ].map((f) => (
            <View key={f} style={styles.feature}>
              <Ionicons name="checkmark-circle" size={18} color="#22c55e" />
              <Text style={styles.featureText}>{f}</Text>
            </View>
          ))}
        </View>

        {Platform.OS === "web" ? (
          <View style={styles.webNotice}>
            <Text style={styles.webNoticeText}>
              Bank linking uses Plaid's native SDK, so it runs in the iOS/Android app (development build), not in the
              browser. To explore on the web, sign in with the demo account created by
              {" "}<Text style={styles.code}>python -m app.seed_demo</Text>.
            </Text>
          </View>
        ) : (
          <TouchableOpacity style={styles.button} onPress={handleConnect} disabled={loading}>
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>{reconnectId !== null ? "Sign in to your bank again" : "Connect a Bank Account"}</Text>
            )}
          </TouchableOpacity>
        )}

        <Text style={styles.disclaimer}>
          Sandbox mode: choose any bank and sign in with user_good / pass_good
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  inner: { flex: 1, paddingHorizontal: 24, paddingTop: 8 },
  back: { marginBottom: 24 },
  title: { fontSize: 26, fontWeight: "700", color: "#f8fafc", marginBottom: 10 },
  subtitle: { color: "#94a3b8", fontSize: 14, lineHeight: 22, marginBottom: 32 },
  featureList: { gap: 12, marginBottom: 40 },
  feature: { flexDirection: "row", alignItems: "center", gap: 10 },
  featureText: { color: "#cbd5e1", fontSize: 14 },
  button: {
    backgroundColor: "#6366f1",
    borderRadius: 14,
    padding: 18,
    alignItems: "center",
  },
  buttonText: { color: "#fff", fontWeight: "600", fontSize: 16 },
  webNotice: {
    backgroundColor: "#1e293b",
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: "#334155",
  },
  webNoticeText: { color: "#cbd5e1", fontSize: 13, lineHeight: 20 },
  code: { fontFamily: Platform.OS === "web" ? "monospace" : undefined, color: "#a5b4fc" },
  disclaimer: { color: "#475569", fontSize: 12, textAlign: "center", marginTop: 20 },
});
