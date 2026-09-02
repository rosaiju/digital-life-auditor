import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuthStore } from "@/store/auth";
import { plaidApi } from "@/services/api";

export default function Settings() {
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);

  async function handleSync() {
    try {
      await plaidApi.sync();
      Alert.alert("Success", "Transactions synced successfully");
    } catch (e: any) {
      Alert.alert("Sync failed", e?.response?.data?.detail ?? "No connected accounts");
    }
  }

  function handleLogout() {
    Alert.alert("Sign Out", "Are you sure you want to sign out?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Sign Out",
        style: "destructive",
        onPress: logout,
      },
    ]);
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <Text style={styles.title}>Settings</Text>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>ACCOUNTS</Text>

          <TouchableOpacity
            style={styles.row}
            onPress={() => router.push("/connect-bank")}
          >
            <Ionicons name="link-outline" size={20} color="#6366f1" />
            <Text style={styles.rowText}>Connect Bank Account</Text>
            <Ionicons name="chevron-forward" size={16} color="#475569" />
          </TouchableOpacity>

          <TouchableOpacity style={styles.row} onPress={handleSync}>
            <Ionicons name="refresh-outline" size={20} color="#6366f1" />
            <Text style={styles.rowText}>Sync Transactions Now</Text>
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
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  inner: { flex: 1, paddingHorizontal: 20, paddingTop: 16 },
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
  rowText: { flex: 1, color: "#f8fafc", fontSize: 15 },
  rowValue: { color: "#64748b", fontSize: 14 },
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
