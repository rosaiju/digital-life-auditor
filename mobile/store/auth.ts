import * as SecureStore from "expo-secure-store";
import { create } from "zustand";

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
    await SecureStore.setItemAsync("access_token", token);
    set({ token });
  },

  loadToken: async () => {
    const token = await SecureStore.getItemAsync("access_token");
    set({ token, isLoading: false });
  },

  logout: async () => {
    await SecureStore.deleteItemAsync("access_token");
    set({ token: null });
  },
}));
