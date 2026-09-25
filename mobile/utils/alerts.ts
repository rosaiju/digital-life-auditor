import { Alert, Platform } from "react-native";

/** Cross-platform alert: Alert.alert does nothing on web, so fall back to window.alert. */
export function showAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    window.alert(`${title}: ${message}`);
  } else {
    Alert.alert(title, message);
  }
}

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel: string;
  destructive?: boolean;
}

/** Cross-platform confirmation dialog; calls onConfirm only if the user agrees. */
export function confirm({ title, message, confirmLabel, destructive }: ConfirmOptions, onConfirm: () => void) {
  if (Platform.OS === "web") {
    if (window.confirm(`${title}\n\n${message}`)) onConfirm();
    return;
  }
  Alert.alert(title, message, [
    { text: "Cancel", style: "cancel" },
    { text: confirmLabel, style: destructive ? "destructive" : "default", onPress: onConfirm },
  ]);
}

/** Best available human-readable message from an axios error. */
export function errorMessage(e: any, fallback = "Something went wrong"): string {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (e?.code === "ERR_NETWORK") return "Can't reach the server. Is the backend running?";
  return e?.message ?? fallback;
}
