import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { PlaidLink, LinkSuccess, LinkExit } from "react-native-plaid-link-sdk";
import { useQueryClient } from "@tanstack/react-query";
import { plaidApi } from "@/services/api";
import { Ionicons } from "@expo/vector-icons";

export default function ConnectBank() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function fetchLinkToken() {
    setLoading(true);
    try {
      const res = await plaidApi.getLinkToken();
      setLinkToken(res.data.link_token);
    } catch (e: any) {
      Alert.alert("Error", "Failed to initialize bank connection");
    } finally {
      setLoading(false);
    }
  }

  async function onPlaidSuccess(success: LinkSuccess) {
    try {
      await plaidApi.exchange(
        success.publicToken,
        success.metadata.institution?.name
      );
      await queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
      Alert.alert(
        "Connected!",
        "Your bank is connected. Scanning for subscriptions...",
        [{ text: "OK", onPress: () => router.replace("/(tabs)") }]
      );
    } catch (e) {
      Alert.alert("Error", "Failed to connect bank account");
    }
  }

  function onPlaidExit(exit: LinkExit) {
    if (exit.error) {
      Alert.alert("Connection cancelled", exit.error.displayMessage ?? "Try again");
    }
    setLinkToken(null);
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <TouchableOpacity style={styles.back} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={22} color="#94a3b8" />
        </TouchableOpacity>

        <Text style={styles.title}>Connect Your Bank</Text>
        <Text style={styles.subtitle}>
          We use Plaid to securely connect to your bank. We never store your
          credentials and only read transaction history.
        </Text>

        <View style={styles.featureList}>
          {[
            "Bank-level 256-bit encryption",
            "Read-only access — we can't move money",
            "Powered by Plaid, trusted by millions",
          ].map((f) => (
            <View key={f} style={styles.feature}>
              <Ionicons name="checkmark-circle" size={18} color="#22c55e" />
              <Text style={styles.featureText}>{f}</Text>
            </View>
          ))}
        </View>

        {linkToken ? (
          <PlaidLink
            tokenConfig={{ token: linkToken }}
            onSuccess={onPlaidSuccess}
            onExit={onPlaidExit}
          >
            <View style={styles.button}>
              <Text style={styles.buttonText}>Open Plaid</Text>
            </View>
          </PlaidLink>
        ) : (
          <TouchableOpacity
            style={styles.button}
            onPress={fetchLinkToken}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Connect a Bank Account</Text>
            )}
          </TouchableOpacity>
        )}

        <Text style={styles.disclaimer}>
          Sandbox mode: use Chase → user_good / pass_good to test
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
  disclaimer: { color: "#334155", fontSize: 12, textAlign: "center", marginTop: 20 },
});
