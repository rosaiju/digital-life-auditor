import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { FlatList } from "react-native";
import Dashboard from "@/app/(tabs)/index";
import { apiMock, apiError, resetApiMock } from "../test-utils/apiMock";
import { alertSpy, pressAlertButton, renderScreen, resetApp, router } from "../test-utils/render";

jest.mock("@/services/api", () => require("../test-utils/apiMock").apiMock);

const sub = (over: Record<string, unknown> = {}) => ({
  id: 1,
  merchant_name: "netflix",
  display_name: "Netflix",
  amount: 15.49,
  frequency: "monthly",
  category: "Entertainment",
  last_charge_date: "2026-09-01",
  next_charge_date: "2026-10-01",
  confidence: 0.9,
  status: "active",
  cancel_url: "https://netflix.com/cancel",
  monthly_cost: 15.49,
  ...over,
});

const bank = (over: Record<string, unknown> = {}) => ({
  id: 5,
  institution_name: "Chase",
  connected_at: "2026-09-01T00:00:00",
  status: "ok",
  last_synced_at: "2026-09-25T00:00:00",
  last_error: null,
  ...over,
});

function serve({ active = [sub()], ended = [] as any[], items = [bank()] as any[] } = {}) {
  apiMock.subscriptionsApi.list.mockImplementation(async (status: string) => ({
    data: status === "active" ? active : status === "ended" ? ended : [],
  }));
  apiMock.plaidApi.items.mockResolvedValue({ data: items });
}

const refresh = () =>
  act(async () => {
    await screen.UNSAFE_getByType(FlatList).props.refreshControl.props.onRefresh();
  });

let alert: jest.SpyInstance;
beforeEach(() => {
  resetApp();
  resetApiMock();
  alert = alertSpy();
});
afterEach(() => alert.mockRestore());

describe("Dashboard", () => {
  it("lists subscriptions with a monthly total", async () => {
    serve({ active: [sub(), sub({ id: 2, merchant_name: "spotify", display_name: "Spotify", amount: 10.99, monthly_cost: 10.99, next_charge_date: "2026-10-05" })] });
    renderScreen(<Dashboard />);

    expect(await screen.findByText("Netflix")).toBeTruthy();
    expect(screen.getByText("Spotify")).toBeTruthy();
    expect(screen.getByText("$26.48")).toBeTruthy(); // 15.49 + 10.99
    expect(screen.getByText("Next: Oct 1")).toBeTruthy(); // not shifted a day by the time zone
  });

  it("shows the empty state with a way to connect a bank", async () => {
    serve({ active: [] });
    renderScreen(<Dashboard />);
    fireEvent.press(await screen.findByText("Connect Bank"));
    expect(router().push).toHaveBeenCalledWith("/connect-bank");
  });

  it("shows nothing misleading while the first load is in flight", () => {
    apiMock.subscriptionsApi.list.mockReturnValue(new Promise(() => {}));
    apiMock.plaidApi.items.mockReturnValue(new Promise(() => {}));
    renderScreen(<Dashboard />);
    expect(screen.queryByText("No subscriptions found")).toBeNull();
    expect(screen.queryByText("Couldn't load subscriptions")).toBeNull();
  });

  it("does not fetch anything before the saved login has loaded", () => {
    resetApp({ signedIn: false });
    renderScreen(<Dashboard />);
    expect(apiMock.subscriptionsApi.list).not.toHaveBeenCalled();
  });

  it("shows an error state and recovers on retry", async () => {
    apiMock.plaidApi.items.mockResolvedValue({ data: [] });
    apiMock.subscriptionsApi.list.mockRejectedValue({ code: "ERR_NETWORK" });
    renderScreen(<Dashboard />);
    expect(await screen.findByText("Couldn't load subscriptions")).toBeTruthy();
    expect(screen.getByText(/Can't reach the server/)).toBeTruthy();

    serve();
    fireEvent.press(screen.getByText("Try again"));
    expect(await screen.findByText("Netflix")).toBeTruthy();
  });

  it("asks a bank whose login expired to reconnect", async () => {
    serve({ items: [bank({ status: "login_required" })] });
    renderScreen(<Dashboard />);

    expect(await screen.findByText(/Chase needs you to sign in again/)).toBeTruthy();
    fireEvent.press(screen.getByText("Reconnect"));
    expect(router().push).toHaveBeenCalledWith({ pathname: "/connect-bank", params: { itemId: "5" } });
  });

  it("mentions subscriptions that appear to have ended, separately from the total", async () => {
    serve({ ended: [sub({ id: 3, merchant_name: "peloton", display_name: "Peloton", status: "ended" })] });
    renderScreen(<Dashboard />);
    expect(await screen.findByText(/No recent charge from Peloton/)).toBeTruthy();
    expect(screen.queryByText("Peloton")).toBeNull(); // no card for it, and it is not in the count
    expect(screen.getAllByLabelText(/^Dismiss /)).toHaveLength(1); // only Netflix has a card
  });

  it("dismisses only after confirmation, then reloads the list", async () => {
    serve();
    apiMock.subscriptionsApi.dismiss.mockResolvedValue({ data: sub({ status: "dismissed" }) });
    renderScreen(<Dashboard />);
    await screen.findByText("Netflix");

    fireEvent.press(screen.getByLabelText("Dismiss Netflix"));
    expect(apiMock.subscriptionsApi.dismiss).not.toHaveBeenCalled(); // asked first

    serve({ active: [] });
    pressAlertButton(alert, "Dismiss");
    await waitFor(() => expect(apiMock.subscriptionsApi.dismiss).toHaveBeenCalledWith(1));
    expect(await screen.findByText("No subscriptions found")).toBeTruthy();
  });

  it("tells the user when dismissing fails", async () => {
    serve();
    apiMock.subscriptionsApi.dismiss.mockRejectedValue(apiError(500, "db down"));
    renderScreen(<Dashboard />);
    await screen.findByText("Netflix");

    fireEvent.press(screen.getByLabelText("Dismiss Netflix"));
    pressAlertButton(alert, "Dismiss");

    await waitFor(() => expect(alert).toHaveBeenCalledWith("Couldn't dismiss", "db down"));
    expect(screen.getByText("Netflix")).toBeTruthy();
  });

  describe("pull to refresh", () => {
    it("syncs the bank, then reloads", async () => {
      serve();
      apiMock.plaidApi.sync.mockResolvedValue({ data: { status: "synced", failed: [] } });
      renderScreen(<Dashboard />);
      await screen.findByText("Netflix");
      apiMock.subscriptionsApi.list.mockClear();

      await refresh();

      expect(apiMock.plaidApi.sync).toHaveBeenCalledTimes(1);
      expect(apiMock.subscriptionsApi.list).toHaveBeenCalledWith("active");
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("stays quiet when no bank is connected yet (404)", async () => {
      serve({ items: [] });
      apiMock.plaidApi.sync.mockRejectedValue(apiError(404, "No connected accounts"));
      renderScreen(<Dashboard />);
      await screen.findByText("Netflix");
      await refresh();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("shows why a sync failed instead of swallowing it", async () => {
      serve();
      apiMock.plaidApi.sync.mockRejectedValue(apiError(502, "Bank provider error: institution is down"));
      renderScreen(<Dashboard />);
      await screen.findByText("Netflix");
      await refresh();
      expect(screen.getByText("Bank provider error: institution is down")).toBeTruthy();
      expect(screen.getByText("Netflix")).toBeTruthy(); // cached list stays visible
    });

    it("names the banks that failed when only some synced", async () => {
      serve();
      apiMock.plaidApi.sync.mockResolvedValue({
        data: { status: "partial", failed: [{ id: 5, institution_name: "Chase", status: "error", error: "down" }] },
      });
      renderScreen(<Dashboard />);
      await screen.findByText("Netflix");
      await refresh();
      expect(screen.getByText("Couldn't sync Chase.")).toBeTruthy();
    });
  });
});
