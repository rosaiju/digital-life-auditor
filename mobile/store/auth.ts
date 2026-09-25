import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { create } from "zustand";

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
    await storage.setItem("access_token", token);
    set({ token });
  },

  loadToken: async () => {
    const token = await storage.getItem("access_token");
    set({ token, isLoading: false });
  },

  logout: async () => {
    await storage.deleteItem("access_token");
    set({ token: null });
  },
}));
