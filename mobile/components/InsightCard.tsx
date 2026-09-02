import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { Insight } from "@/hooks/useInsights";

const TYPE_CONFIG = {
  redundant: { icon: "copy-outline" as const, color: "#f59e0b", bg: "#1c1408" },
  savings: { icon: "trending-down-outline" as const, color: "#22c55e", bg: "#051a0d" },
  warning: { icon: "warning-outline" as const, color: "#ef4444", bg: "#1c0808" },
  tip: { icon: "bulb-outline" as const, color: "#6366f1", bg: "#0d0d1c" },
};

interface Props {
  insight: Insight;
}

export function InsightCard({ insight }: Props) {
  const config = TYPE_CONFIG[insight.type] ?? TYPE_CONFIG.tip;

  return (
    <View style={[styles.card, { backgroundColor: config.bg, borderColor: config.color + "33" }]}>
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: config.color + "22" }]}>
          <Ionicons name={config.icon} size={16} color={config.color} />
        </View>
        <Text style={[styles.title, { color: config.color }]}>{insight.title}</Text>
        {insight.potential_savings > 0 && (
          <Text style={styles.savings}>
            Save ${insight.potential_savings.toFixed(0)}/mo
          </Text>
        )}
      </View>
      <Text style={styles.detail}>{insight.detail}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
  },
  header: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  iconWrap: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  title: { flex: 1, fontWeight: "600", fontSize: 14 },
  savings: {
    backgroundColor: "#052e16",
    color: "#22c55e",
    fontSize: 11,
    fontWeight: "600",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  detail: { color: "#94a3b8", fontSize: 13, lineHeight: 20 },
});
