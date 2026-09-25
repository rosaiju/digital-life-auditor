import { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { confirm } from "@/utils/alerts";

export interface PasswordField {
  key: string;
  placeholder: string;
  autoComplete: "current-password" | "new-password";
}

interface Props {
  title: string;
  description: string;
  fields: PasswordField[];
  submitLabel: string;
  destructive?: boolean;
  /** Asks "are you sure?" after the fields validate, before submitting. */
  confirmation?: { title: string; message: string; confirmLabel: string };
  /** Return an error message to show, or null when the values are acceptable. */
  validate?: (values: Record<string, string>) => string | null;
  onSubmit: (values: Record<string, string>) => Promise<void>;
  errorMessage: (e: unknown) => string;
}

/** A back-navigable screen with password inputs and one submit button (change password, delete account). */
export function PasswordForm({
  title,
  description,
  fields,
  submitLabel,
  destructive,
  confirmation,
  validate,
  onSubmit,
  errorMessage,
}: Props) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    setLoading(true);
    try {
      await onSubmit(values);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  function submit() {
    if (loading) return;
    const problem = fields.some((f) => !values[f.key]) ? "Please fill in every field" : validate?.(values) ?? null;
    if (problem) {
      setError(problem);
      return;
    }
    if (confirmation) confirm({ ...confirmation, destructive }, run);
    else void run();
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <TouchableOpacity style={styles.back} onPress={() => router.back()} accessibilityLabel="Go back">
          <Ionicons name="arrow-back" size={22} color="#94a3b8" />
        </TouchableOpacity>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.description}>{description}</Text>

        {fields.map((f, i) => (
          <TextInput
            key={f.key}
            style={styles.input}
            placeholder={f.placeholder}
            placeholderTextColor="#64748b"
            secureTextEntry
            autoComplete={f.autoComplete}
            returnKeyType={i === fields.length - 1 ? "go" : "next"}
            onSubmitEditing={i === fields.length - 1 ? submit : undefined}
            value={values[f.key] ?? ""}
            onChangeText={(text) => setValues((v) => ({ ...v, [f.key]: text }))}
          />
        ))}

        {error && (
          <Text style={styles.error} accessibilityRole="alert">
            {error}
          </Text>
        )}

        <TouchableOpacity
          style={[styles.button, destructive && styles.buttonDestructive]}
          onPress={submit}
          disabled={loading}
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{submitLabel}</Text>}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  inner: { flex: 1, paddingHorizontal: 24, paddingTop: 8 },
  back: { marginBottom: 24 },
  title: { fontSize: 26, fontWeight: "700", color: "#f8fafc", marginBottom: 10 },
  description: { color: "#94a3b8", fontSize: 14, lineHeight: 22, marginBottom: 28 },
  input: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    padding: 16,
    color: "#f8fafc",
    fontSize: 15,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: "#334155",
  },
  error: { color: "#f87171", fontSize: 13, marginBottom: 12 },
  button: { backgroundColor: "#6366f1", borderRadius: 12, padding: 16, alignItems: "center", marginTop: 6 },
  buttonDestructive: { backgroundColor: "#dc2626" },
  buttonText: { color: "#fff", fontWeight: "600", fontSize: 16 },
});
