import { View, Text, StyleSheet } from "react-native";

interface Props {
  monthlyTotal: number;
  count: number;
}

export function SummaryBanner({ monthlyTotal, count }: Props) {
  const yearlyTotal = monthlyTotal * 12;

  return (
    <View style={styles.card}>
      <Text style={styles.label}>Monthly Spend</Text>
      <Text style={styles.total}>${monthlyTotal.toFixed(2)}</Text>

      <View style={styles.row}>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{count}</Text>
          <Text style={styles.statLabel}>Subscriptions</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.stat}>
          <Text style={styles.statValue}>${yearlyTotal.toFixed(0)}</Text>
          <Text style={styles.statLabel}>Per Year</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.stat}>
          <Text style={styles.statValue}>
            ${count > 0 ? (monthlyTotal / count).toFixed(2) : "0"}
          </Text>
          <Text style={styles.statLabel}>Avg/Sub</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#1e293b",
    borderRadius: 18,
    padding: 22,
    marginBottom: 20,
    marginTop: 8,
    borderWidth: 1,
    borderColor: "#334155",
  },
  label: { color: "#64748b", fontSize: 12, fontWeight: "600", letterSpacing: 0.5 },
  total: {
    color: "#f8fafc",
    fontSize: 42,
    fontWeight: "700",
    marginTop: 4,
    marginBottom: 20,
  },
  row: { flexDirection: "row", alignItems: "center" },
  stat: { flex: 1, alignItems: "center" },
  statValue: { color: "#f8fafc", fontSize: 16, fontWeight: "600" },
  statLabel: { color: "#64748b", fontSize: 11, marginTop: 2 },
  divider: { width: 1, height: 30, backgroundColor: "#334155" },
});
