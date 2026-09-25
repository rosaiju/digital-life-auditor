import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { create } from "zustand";
import { queryClient } from "@/services/queryClient";

const storage = {
  getItem: (key: string) =>
    Platform.OS === "web"
      ? Promise.resolve(localStorage.getItem(key))
      : SecureStore.getItemAsync(key),
  setItem: (key: string, value: string) =>
    Platform.OS === "web"
      ? Promise.resolve(localStorage.setItem(key, value))
      : SecureStore.setItemAsync(key, value),
  deleteItem: (key: string) =>
    Platform.OS === "web"
      ? Promise.resolve(localStorage.removeItem(key))
      : SecureStore.deleteItemAsync(key),
};

interface AuthState {
  token: string | null;
  isLoading: boolean;
  setToken: (token: string) => Promise<void>;
  loadToken: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  isLoading: true,

  setToken: async (token) => {
    queryClient.clear(); // never show a previous session's data to whoever signs in next
    await storage.setItem("access_token", token);
    set({ token });
  },

  loadToken: async () => {
    let token: string | null = null;
    try {
      token = await storage.getItem("access_token");
    } catch {
      // unreadable secure storage: treat as signed out rather than hanging on the splash state
    }
    set({ token, isLoading: false });
  },

  logout: async () => {
    queryClient.clear();
    set({ token: null });
    try {
      await storage.deleteItem("access_token");
    } catch {
      // the in-memory token is already gone; a stale stored one is rejected by the server
    }
  },
}));
