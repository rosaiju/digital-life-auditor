import axios from "axios";
import { Platform, Alert } from "react-native";
import * as SecureStore from "expo-secure-store";

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

const getToken = () =>
  Platform.OS === "web"
    ? Promise.resolve(localStorage.getItem("access_token"))
    : SecureStore.getItemAsync("access_token");

export const showAlert = (title: string, message: string) => {
  if (Platform.OS === "web") {
    window.alert(`${title}: ${message}`);
  } else {
    Alert.alert(title, message);
  }
};

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT to every request
api.interceptors.request.use(async (config) => {
  const token = await getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth
export const authApi = {
  register: (email: string, password: string) =>
    api.post("/auth/register", { email, password }),
  login: (email: string, password: string) =>
    api.post(
      "/auth/login",
      new URLSearchParams({ username: email, password }),
      { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
    ),
  me: () => api.get("/auth/me"),
};

// Plaid
export const plaidApi = {
  getLinkToken: () => api.post("/plaid/link-token"),
  exchange: (publicToken: string, institutionName?: string) =>
    api.post("/plaid/exchange", {
      public_token: publicToken,
      institution_name: institutionName,
    }),
  sync: () => api.post("/plaid/sync"),
};

// Subscriptions
export const subscriptionsApi = {
  list: (status: "active" | "dismissed" | "all" = "active") =>
    api.get("/subscriptions", { params: { status } }),
  dismiss: (id: number) => api.patch(`/subscriptions/${id}/dismiss`),
  restore: (id: number) => api.patch(`/subscriptions/${id}/restore`),
};

// Insights
export const insightsApi = {
  get: () => api.get("/insights"),
  generate: () => api.post("/insights/generate"),
};
