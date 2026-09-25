import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { Link } from "expo-router";
import { authApi } from "@/services/api";
import { showAlert, errorMessage } from "@/utils/alerts";
import { useAuthStore } from "@/store/auth";
import { normalizeEmail, validateCredentials } from "@/utils/validation";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const setToken = useAuthStore((s) => s.setToken);

  async function handleLogin() {
    if (loading) return;
    const cleanEmail = normalizeEmail(email);
    const problem = validateCredentials(cleanEmail, password);
    if (problem) {
      showAlert("Check your details", problem);
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.login(cleanEmail, password);
      await setToken(res.data.access_token);
    } catch (e: any) {
      showAlert("Login failed", errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.inner}>
        <Text style={styles.logo}>Digital Life Auditor</Text>
        <Text style={styles.tagline}>Know what you're paying for.</Text>

        <TextInput
          style={styles.input}
          placeholder="Email"
          placeholderTextColor="#64748b"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          keyboardType="email-address"
          returnKeyType="next"
          value={email}
          onChangeText={setEmail}
        />
        <TextInput
          style={styles.input}
          placeholder="Password"
          placeholderTextColor="#64748b"
          secureTextEntry
          autoComplete="current-password"
          returnKeyType="go"
          onSubmitEditing={handleLogin}
          value={password}
          onChangeText={setPassword}
        />

        <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Sign In</Text>
          )}
        </TouchableOpacity>

        <Link href="/(auth)/register" asChild>
          <TouchableOpacity style={styles.link}>
            <Text style={styles.linkText}>
              Don't have an account?{" "}
              <Text style={styles.linkAccent}>Sign up</Text>
            </Text>
          </TouchableOpacity>
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  inner: { flex: 1, justifyContent: "center", paddingHorizontal: 28 },
  logo: { fontSize: 28, fontWeight: "700", color: "#f8fafc", marginBottom: 6 },
  tagline: { fontSize: 15, color: "#94a3b8", marginBottom: 40 },
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
  button: {
    backgroundColor: "#6366f1",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 6,
  },
  buttonText: { color: "#fff", fontWeight: "600", fontSize: 16 },
  link: { marginTop: 24, alignItems: "center" },
  linkText: { color: "#64748b", fontSize: 14 },
  linkAccent: { color: "#6366f1", fontWeight: "600" },
});
