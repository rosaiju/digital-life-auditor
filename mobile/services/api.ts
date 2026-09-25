import axios from "axios";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { useAuthStore } from "@/store/auth";

// Android emulators reach the host machine at 10.0.2.2; set EXPO_PUBLIC_API_URL for a real device.
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

const getToken = () =>
  Platform.OS === "web"
    ? Promise.resolve(localStorage.getItem("access_token"))
    : SecureStore.getItemAsync("access_token");

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 60_000, // the first bank sync can take a while
});

// Attach JWT to every request
api.interceptors.request.use(async (config) => {
  const token = await getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// An expired or revoked token sends the user back to the login screen instead of leaving
// every screen showing errors. (A failed login has no token yet, so it is left alone.)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && error.config?.headers?.Authorization) {
      void useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  }
);

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
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword }),
  deleteAccount: (password: string) => api.post("/auth/delete-account", { password }),
};

export interface SyncResult {
  status: string;
  accounts?: number;
  transactions_added?: number;
  subscriptions_found?: number;
  synced?: boolean;
  /** Banks that failed while others succeeded (status "partial"). */
  failed?: { id: number; institution_name: string | null; status: string; error: string }[];
}

export interface PlaidItem {
  id: number;
  institution_name: string | null;
  connected_at: string;
  /** "login_required" means the user must sign in to their bank again (Reconnect). */
  status: "ok" | "login_required" | "error";
  last_synced_at: string | null;
  last_error: string | null;
}

// Plaid
export const plaidApi = {
  getLinkToken: () => api.post<{ link_token: string }>("/plaid/link-token"),
  exchange: (publicToken: string, institutionName?: string) =>
    api.post<SyncResult>("/plaid/exchange", {
      public_token: publicToken,
      institution_name: institutionName,
    }),
  sync: () => api.post<SyncResult>("/plaid/sync"),
  items: () => api.get<PlaidItem[]>("/plaid/items"),
  disconnect: (id: number) => api.delete(`/plaid/items/${id}`),
  reconnectLinkToken: (id: number) => api.post<{ link_token: string }>(`/plaid/items/${id}/link-token`),
  reconnected: (id: number) => api.post<SyncResult>(`/plaid/items/${id}/reconnected`),
};

// Subscriptions
export const subscriptionsApi = {
  list: (status: "active" | "dismissed" | "ended" | "all" = "active") =>
    api.get("/subscriptions", { params: { status } }),
  dismiss: (id: number) => api.patch(`/subscriptions/${id}/dismiss`),
  restore: (id: number) => api.patch(`/subscriptions/${id}/restore`),
};

// Insights
export const insightsApi = {
  get: () => api.get("/insights"),
  generate: () => api.post("/insights/generate"),
};
