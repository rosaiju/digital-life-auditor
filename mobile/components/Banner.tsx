import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface Props {
  message: string;
  tone?: "warning" | "error";
  actionLabel?: string;
  onAction?: () => void;
}

/** An inline notice above a list: a bank needing attention, or a failed background sync. */
export function Banner({ message, tone = "warning", actionLabel, onAction }: Props) {
  const color = tone === "error" ? "#ef4444" : "#f59e0b";
  return (
    <View style={[styles.container, { borderColor: color }]} accessibilityRole="alert">
      <Ionicons name="alert-circle-outline" size={20} color={color} />
      <Text style={styles.message}>{message}</Text>
      {actionLabel && onAction && (
        <TouchableOpacity onPress={onAction} hitSlop={8}>
          <Text style={[styles.action, { color }]}>{actionLabel}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: "#1e293b",
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    marginBottom: 12,
  },
  message: { flex: 1, color: "#e2e8f0", fontSize: 13, lineHeight: 18 },
  action: { fontWeight: "700", fontSize: 13 },
});
