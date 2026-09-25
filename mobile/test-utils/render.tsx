import { ReactElement } from "react";
import { Alert } from "react-native";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react-native";
import { queryClient } from "@/services/queryClient";
import { useAuthStore } from "@/store/auth";

/** Fresh cache and a signed-in user, no retries so failures show up immediately. */
export function resetApp({ signedIn = true } = {}) {
  queryClient.clear();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: 0, gcTime: Infinity } });
  useAuthStore.setState({ token: signedIn ? "test-token" : null, isLoading: false });
  jest.clearAllMocks();
  const { __router } = require("expo-router");
  Object.values(__router).forEach((fn) => (fn as jest.Mock).mockClear());
  (require("expo-router").useLocalSearchParams as jest.Mock).mockReturnValue({});
}

export function renderScreen(ui: ReactElement) {
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

export const router = () => require("expo-router").__router as Record<"push" | "replace" | "back", jest.Mock>;

export function alertSpy() {
  return jest.spyOn(Alert, "alert").mockImplementation(() => {});
}

/** Press a button of the most recent Alert.alert(...) dialog by its label. */
export function pressAlertButton(spy: jest.SpyInstance, label: string) {
  const buttons = spy.mock.calls[spy.mock.calls.length - 1][2] as { text: string; onPress?: () => void }[];
  const button = buttons.find((b) => b.text === label);
  if (!button?.onPress) throw new Error(`No "${label}" button in the last alert`);
  button.onPress();
}

/** Let in-flight promises and queries finish inside act(), so late state updates don't warn. */
export const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

afterEach(settle);
