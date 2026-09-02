import { View, Text, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { Subscription } from "@/hooks/useSubscriptions";

const CATEGORY_COLORS: Record<string, string> = {
  Entertainment: "#7c3aed",
  Productivity: "#0284c7",
  "Health & Wellness": "#059669",
  Education: "#d97706",
  News: "#dc2626",
  "AI Tools": "#6366f1",
  "Developer Tools": "#0f766e",
  Shopping: "#c026d3",
  Career: "#0369a1",
  default: "#475569",
};

const FREQUENCY_LABELS: Record<string, string> = {
  weekly: "wk",
  biweekly: "2wk",
  monthly: "mo",
  quarterly: "qtr",
  annual: "yr",
};

interface Props {
  subscription: Subscription;
  onDismiss: () => void;
}

export function SubscriptionCard({ subscription: s, onDismiss }: Props) {
  const color = CATEGORY_COLORS[s.category ?? "default"] ?? CATEGORY_COLORS.default;

  function confirmDismiss() {
    Alert.alert(
      "Dismiss subscription",
      `Remove "${s.display_name ?? s.merchant_name}" from your list?`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Dismiss", style: "destructive", onPress: onDismiss },
      ]
    );
  }

  const nextCharge = s.next_charge_date
    ? new Date(s.next_charge_date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <View style={styles.card}>
      {/* Left accent bar */}
      <View style={[styles.accent, { backgroundColor: color }]} />

      <View style={styles.content}>
        {/* Top row */}
        <View style={styles.topRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name} numberOfLines={1}>
              {s.display_name ?? s.merchant_name}
            </Text>
            {s.category && (
              <Text style={[styles.category, { color }]}>{s.category}</Text>
            )}
          </View>

          <View style={styles.priceBlock}>
            <Text style={styles.amount}>${s.amount.toFixed(2)}</Text>
            <Text style={styles.frequency}>/{FREQUENCY_LABELS[s.frequency] ?? s.frequency}</Text>
          </View>
        </View>

        {/* Bottom row */}
        <View style={styles.bottomRow}>
          {nextCharge && (
            <View style={styles.nextCharge}>
              <Ionicons name="calendar-outline" size={12} color="#64748b" />
              <Text style={styles.nextChargeText}>Next: {nextCharge}</Text>
            </View>
          )}
          <View style={styles.monthlyCost}>
            <Text style={styles.monthlyCostText}>
              ${s.monthly_cost.toFixed(2)}/mo
            </Text>
          </View>
          <TouchableOpacity style={styles.dismissBtn} onPress={confirmDismiss}>
            <Ionicons name="close" size={14} color="#475569" />
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    backgroundColor: "#1e293b",
    borderRadius: 14,
    marginBottom: 10,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#334155",
  },
  accent: { width: 4 },
  content: { flex: 1, padding: 14 },
  topRow: { flexDirection: "row", alignItems: "flex-start", marginBottom: 8 },
  name: { color: "#f8fafc", fontSize: 15, fontWeight: "600" },
  category: { fontSize: 11, fontWeight: "500", marginTop: 2 },
  priceBlock: { flexDirection: "row", alignItems: "baseline", gap: 2 },
  amount: { color: "#f8fafc", fontSize: 17, fontWeight: "700" },
  frequency: { color: "#64748b", fontSize: 12 },
  bottomRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  nextCharge: { flexDirection: "row", alignItems: "center", gap: 4 },
  nextChargeText: { color: "#64748b", fontSize: 12 },
  monthlyCost: { flex: 1 },
  monthlyCostText: { color: "#94a3b8", fontSize: 11 },
  dismissBtn: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "#0f172a",
    alignItems: "center",
    justifyContent: "center",
  },
});
