import { AxiosError } from "axios";
import * as SecureStore from "expo-secure-store";
import { api } from "@/services/api";
import { queryClient } from "@/services/queryClient";
import { useAuthStore } from "@/store/auth";

const secure = SecureStore as jest.Mocked<typeof SecureStore>;

beforeEach(async () => {
  queryClient.clear();
  await SecureStore.deleteItemAsync("access_token");
  useAuthStore.setState({ token: null, isLoading: true });
  jest.clearAllMocks();
});

describe("auth store", () => {
  it("logout clears the stored token and every cached query", async () => {
    await useAuthStore.getState().setToken("alice-token");
    queryClient.setQueryData(["subscriptions", "active"], [{ id: 1, display_name: "Alice Netflix" }]);

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().token).toBeNull();
    expect(await SecureStore.getItemAsync("access_token")).toBeNull();
    expect(queryClient.getQueryData(["subscriptions", "active"])).toBeUndefined();
  });

  it("signing in as someone else never shows the previous user's cached data", async () => {
    queryClient.setQueryData(["subscriptions", "active"], [{ id: 1 }]);
    queryClient.setQueryData(["plaid-items"], [{ id: 9 }]);

    await useAuthStore.getState().setToken("bob-token"); // e.g. the old token expired and Bob signs in

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(useAuthStore.getState().token).toBe("bob-token");
  });

  it("loadToken restores a saved session", async () => {
    await SecureStore.setItemAsync("access_token", "saved");
    await useAuthStore.getState().loadToken();
    expect(useAuthStore.getState()).toMatchObject({ token: "saved", isLoading: false });
  });

  it("loadToken falls back to signed out when secure storage fails, instead of hanging", async () => {
    secure.getItemAsync.mockRejectedValueOnce(new Error("keystore unavailable"));
    await useAuthStore.getState().loadToken();
    expect(useAuthStore.getState()).toMatchObject({ token: null, isLoading: false });
  });

  it("logout still signs out when deleting the stored token fails", async () => {
    await useAuthStore.getState().setToken("t");
    secure.deleteItemAsync.mockRejectedValueOnce(new Error("keystore unavailable"));
    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
  });
});

describe("api client", () => {
  function respondWith(status: number, data: unknown = {}) {
    const seen: any[] = [];
    api.defaults.adapter = async (config: any) => {
      seen.push(config);
      const response = { data, status, statusText: "", headers: {}, config };
      if (status >= 400) throw new AxiosError(`HTTP ${status}`, "ERR_BAD_REQUEST", config, null, response as any);
      return response as any;
    };
    return seen;
  }

  it("sends the saved token as a bearer header", async () => {
    await SecureStore.setItemAsync("access_token", "abc");
    const seen = respondWith(200);
    await api.get("/subscriptions");
    expect(seen[0].headers.Authorization).toBe("Bearer abc");
  });

  it("signs the user out when the server rejects their token", async () => {
    await useAuthStore.getState().setToken("expired");
    respondWith(401, { detail: "Invalid or expired token" });

    await expect(api.get("/subscriptions")).rejects.toBeTruthy();

    expect(useAuthStore.getState().token).toBeNull();
  });

  it("does not sign anyone out because a login attempt failed", async () => {
    useAuthStore.setState({ token: "other", isLoading: false });
    await SecureStore.deleteItemAsync("access_token"); // no token stored: like the login screen
    respondWith(401, { detail: "Incorrect email or password" });

    await expect(api.post("/auth/login", {})).rejects.toBeTruthy();

    expect(useAuthStore.getState().token).toBe("other");
  });

  it("leaves other errors alone", async () => {
    await useAuthStore.getState().setToken("t");
    respondWith(500);
    await expect(api.get("/x")).rejects.toBeTruthy();
    expect(useAuthStore.getState().token).toBe("t");
  });
});
