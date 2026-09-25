import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import Settings from "@/app/(tabs)/settings";
import { useAuthStore } from "@/store/auth";
import { apiMock, apiError, resetApiMock } from "../test-utils/apiMock";
import { alertSpy, pressAlertButton, renderScreen, resetApp, router, settle } from "../test-utils/render";

jest.mock("@/services/api", () => require("../test-utils/apiMock").apiMock);

const bank = (over: Record<string, unknown> = {}) => ({
  id: 5,
  institution_name: "Chase",
  connected_at: "2026-09-01T00:00:00",
  status: "ok",
  last_synced_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  last_error: null,
  ...over,
});

function serve(items: any[], dismissed: any[] = []) {
  apiMock.plaidApi.items.mockResolvedValue({ data: items });
  apiMock.subscriptionsApi.list.mockImplementation(async (status: string) => ({ data: status === "dismissed" ? dismissed : [] }));
}

let alert: jest.SpyInstance;
beforeEach(() => {
  resetApp();
  resetApiMock();
  alert = alertSpy();
});
afterEach(() => alert.mockRestore());

describe("Settings: banks", () => {
  it("shows each bank with when it last synced", async () => {
    serve([bank()]);
    renderScreen(<Settings />);
    expect(await screen.findByText("Chase")).toBeTruthy();
    expect(screen.getByText("Synced 5 min ago")).toBeTruthy();
  });

  it("flags a bank that needs a new sign-in and offers to reconnect it", async () => {
    serve([bank({ status: "login_required" })]);
    renderScreen(<Settings />);
    expect(await screen.findByText("Sign-in needed")).toBeTruthy();

    fireEvent.press(screen.getByText("Reconnect"));
    expect(router().push).toHaveBeenCalledWith({ pathname: "/connect-bank", params: { itemId: "5" } });
  });

  it("shows a failed sync without offering Reconnect", async () => {
    serve([bank({ status: "error", last_error: "bank down" })]);
    renderScreen(<Settings />);
    expect(await screen.findByText("Last sync failed")).toBeTruthy();
    expect(screen.queryByText("Reconnect")).toBeNull();
  });

  it("says so when the bank list cannot be loaded", async () => {
    apiMock.plaidApi.items.mockRejectedValue({ code: "ERR_NETWORK" });
    apiMock.subscriptionsApi.list.mockResolvedValue({ data: [] });
    renderScreen(<Settings />);
    expect(await screen.findByText(/Couldn't load your banks/)).toBeTruthy();
  });

  it("disconnects only after confirmation", async () => {
    serve([bank()]);
    apiMock.plaidApi.disconnect.mockResolvedValue({});
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Disconnect"));
    expect(apiMock.plaidApi.disconnect).not.toHaveBeenCalled();

    serve([]);
    await pressAlertButton(alert, "Disconnect");

    await waitFor(() => expect(apiMock.plaidApi.disconnect).toHaveBeenCalledWith(5));
    await waitFor(() => expect(screen.queryByText("Chase")).toBeNull());
  });

  it("reports a failed disconnect", async () => {
    serve([bank()]);
    apiMock.plaidApi.disconnect.mockRejectedValue(apiError(404, "Connection not found"));
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Disconnect"));
    await pressAlertButton(alert, "Disconnect");
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Couldn't disconnect", "Connection not found"));
    await settle();
  });
});

describe("Settings: sync now", () => {
  it("reports new transactions", async () => {
    serve([bank()]);
    apiMock.plaidApi.sync.mockResolvedValue({ data: { status: "synced", transactions_added: 3, failed: [] } });
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Sync Transactions Now"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Synced", "3 new transactions found."));
    await settle();
  });

  it("says when everything is up to date", async () => {
    serve([bank()]);
    apiMock.plaidApi.sync.mockResolvedValue({ data: { status: "synced", transactions_added: 0, failed: [] } });
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Sync Transactions Now"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Synced", "Everything is up to date."));
    await settle();
  });

  it("lists which banks failed on a partial sync", async () => {
    serve([bank()]);
    apiMock.plaidApi.sync.mockResolvedValue({
      data: { status: "partial", transactions_added: 1, failed: [{ id: 5, institution_name: "Chase", status: "error", error: "down" }] },
    });
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Sync Transactions Now"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Some banks didn't sync", "Chase: down"));
    await settle();
  });

  it("explains that no bank is connected instead of calling it a failure", async () => {
    serve([]);
    apiMock.plaidApi.sync.mockRejectedValue(apiError(404, "No connected accounts"));
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Sync Transactions Now"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("No bank connected", "Connect a bank account first, then sync."));
    await settle();
  });

  it("shows the error and re-reads bank status when the sync fails outright", async () => {
    serve([bank()]);
    apiMock.plaidApi.sync.mockRejectedValue(apiError(502, "Bank provider error: login details changed"));
    renderScreen(<Settings />);
    await screen.findByText("Chase");
    apiMock.plaidApi.items.mockClear();

    fireEvent.press(screen.getByText("Sync Transactions Now"));

    await waitFor(() => expect(alert).toHaveBeenCalledWith("Sync failed", "Bank provider error: login details changed"));
    await settle();
    expect(apiMock.plaidApi.items).toHaveBeenCalled();
  });
});

describe("Settings: subscriptions and account", () => {
  it("restores dismissed subscriptions", async () => {
    serve([], [{ id: 1 }, { id: 2 }]);
    apiMock.subscriptionsApi.restore.mockResolvedValue({});
    renderScreen(<Settings />);
    expect(await screen.findByText("2")).toBeTruthy();

    fireEvent.press(screen.getByText("Restore dismissed"));

    await waitFor(() => expect(apiMock.subscriptionsApi.restore).toHaveBeenCalledTimes(2));
  });

  it("disables restore when nothing is dismissed", async () => {
    serve([]);
    renderScreen(<Settings />);
    await screen.findByText("Restore dismissed");
    fireEvent.press(screen.getByText("Restore dismissed"));
    expect(apiMock.subscriptionsApi.restore).not.toHaveBeenCalled();
  });

  it("links to change password and delete account", async () => {
    serve([]);
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Change password"));
    fireEvent.press(screen.getByText("Delete account"));
    expect(router().push).toHaveBeenCalledWith("/change-password");
    expect(router().push).toHaveBeenCalledWith("/delete-account");
    await settle();
  });

  it("signs out after confirmation", async () => {
    serve([]);
    renderScreen(<Settings />);
    fireEvent.press(await screen.findByText("Sign Out"));
    expect(useAuthStore.getState().token).toBe("test-token");
    await pressAlertButton(alert, "Sign Out");
    await waitFor(() => expect(useAuthStore.getState().token).toBeNull());
  });
});
