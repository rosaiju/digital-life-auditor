import { useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { Subscription } from "@/hooks/useSubscriptions";
import { formatShortDate } from "@/utils/dates";

interface Props {
  subscriptions: Subscription[];
}

const FREQUENCY_LABELS: Record<string, string> = {
  weekly: "wk",
  biweekly: "2wk",
  monthly: "mo",
  quarterly: "qtr",
  annual: "yr",
};

/**
 * Subscriptions whose charges stopped, so they are probably cancelled. Kept out of the total
 * but shown here (collapsed by default) so the user can see the detection was not lost.
 */
export function EndedSubscriptions({ subscriptions }: Props) {
  const [open, setOpen] = useState(false);
  if (subscriptions.length === 0) return null;

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.header}
        onPress={() => setOpen((v) => !v)}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`Ended subscriptions, ${subscriptions.length}`}
        accessibilityHint={open ? "Hides the list" : "Shows the list"}
      >
        <Ionicons name="checkmark-done-outline" size={18} color="#64748b" />
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Ended · {subscriptions.length}</Text>
          <Text style={styles.subtitle}>No recent charge, so not counted in your total</Text>
        </View>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color="#64748b" />
      </TouchableOpacity>

      {open &&
        subscriptions.map((s) => (
          <View key={s.id} style={styles.row}>
            <Text style={styles.name} numberOfLines={1}>
              {s.display_name ?? s.merchant_name}
            </Text>
            <Text style={styles.detail} numberOfLines={1}>
              {s.last_charge_date ? `Last charged ${formatShortDate(s.last_charge_date)}` : "No recent charge"} · was $
              {s.amount.toFixed(2)}/{FREQUENCY_LABELS[s.frequency] ?? s.frequency}
            </Text>
          </View>
        ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 8,
    backgroundColor: "#111c33",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1e293b",
    overflow: "hidden",
  },
  header: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14 },
  title: { color: "#94a3b8", fontSize: 14, fontWeight: "600" },
  subtitle: { color: "#64748b", fontSize: 12, marginTop: 2 },
  row: { paddingHorizontal: 14, paddingVertical: 10, borderTopWidth: 1, borderTopColor: "#1e293b" },
  name: { color: "#94a3b8", fontSize: 14 },
  detail: { color: "#64748b", fontSize: 12, marginTop: 2 },
});
