import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { create, open } from "react-native-plaid-link-sdk";
import ConnectBank from "@/app/connect-bank";
import { apiMock, apiError, resetApiMock } from "../test-utils/apiMock";
import { alertSpy, renderScreen, resetApp, router } from "../test-utils/render";

jest.mock("@/services/api", () => require("../test-utils/apiMock").apiMock);
jest.mock("react-native-plaid-link-sdk", () => ({ create: jest.fn(), open: jest.fn() }));

const openMock = open as jest.Mock;
const createMock = create as jest.Mock;
const useParams = () => require("expo-router").useLocalSearchParams as jest.Mock;

let alert: jest.SpyInstance;
beforeEach(() => {
  resetApp();
  resetApiMock();
  openMock.mockReset().mockResolvedValue(undefined);
  createMock.mockReset();
  alert = alertSpy();
});
afterEach(() => alert.mockRestore());

const success = { publicToken: "public-sandbox-1", metadata: { institution: { name: "Tartan Bank" } } };
/** The callbacks the screen handed to Plaid Link's open(). */
const linkCallbacks = () => openMock.mock.calls[0][0] as { onSuccess: (s: any) => Promise<void>; onExit: (e: any) => void };
/** Plaid Link reports back outside React's event system, so wrap it in act like the SDK would. */
const linkSucceeds = () => act(async () => { await linkCallbacks().onSuccess(success); });

describe("connecting a new bank", () => {
  it("creates a link token, opens Plaid Link, then exchanges the public token", async () => {
    apiMock.plaidApi.getLinkToken.mockResolvedValue({ data: { link_token: "link-sandbox-1" } });
    apiMock.plaidApi.exchange.mockResolvedValue({ data: { transactions_added: 331, subscriptions_found: 3 } });
    renderScreen(<ConnectBank />);

    fireEvent.press(screen.getByText("Connect a Bank Account"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());
    expect(createMock).toHaveBeenCalledWith({ token: "link-sandbox-1" });

    await linkSucceeds();

    expect(apiMock.plaidApi.exchange).toHaveBeenCalledWith("public-sandbox-1", "Tartan Bank");
    expect(alert).toHaveBeenCalledWith("Connected!", "Scanned your transactions and found 3 subscriptions.");
    expect(router().replace).toHaveBeenCalledWith("/(tabs)");
  });

  it("uses singular wording for one subscription", async () => {
    apiMock.plaidApi.getLinkToken.mockResolvedValue({ data: { link_token: "l" } });
    apiMock.plaidApi.exchange.mockResolvedValue({ data: { transactions_added: 10, subscriptions_found: 1 } });
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByText("Connect a Bank Account"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());
    await linkSucceeds();
    expect(alert).toHaveBeenCalledWith("Connected!", "Scanned your transactions and found 1 subscription.");
  });

  it("explains that transactions may not be ready yet", async () => {
    apiMock.plaidApi.getLinkToken.mockResolvedValue({ data: { link_token: "l" } });
    apiMock.plaidApi.exchange.mockResolvedValue({ data: { synced: false } });
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByText("Connect a Bank Account"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());
    await linkSucceeds();
    expect(alert).toHaveBeenCalledWith("Connected!", expect.stringContaining("pull down"));
  });

  it("reports a failed token exchange and stays on the screen", async () => {
    apiMock.plaidApi.getLinkToken.mockResolvedValue({ data: { link_token: "l" } });
    apiMock.plaidApi.exchange.mockRejectedValue(apiError(409, "This bank connection belongs to another account"));
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByText("Connect a Bank Account"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());

    await linkSucceeds();

    expect(alert).toHaveBeenCalledWith("Couldn't connect", "This bank connection belongs to another account");
    expect(router().replace).not.toHaveBeenCalled();
  });

  it("reports a failure to get a link token without opening Link", async () => {
    apiMock.plaidApi.getLinkToken.mockRejectedValue(apiError(502, "Bank provider error: invalid client"));
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByText("Connect a Bank Account"));
    await waitFor(() =>
      expect(alert).toHaveBeenCalledWith("Couldn't start bank connection", "Bank provider error: invalid client")
    );
    expect(openMock).not.toHaveBeenCalled();
  });

  it("stays quiet when the user simply closes Link, but surfaces a Link error", async () => {
    apiMock.plaidApi.getLinkToken.mockResolvedValue({ data: { link_token: "l" } });
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByText("Connect a Bank Account"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());

    linkCallbacks().onExit({ error: null });
    expect(alert).not.toHaveBeenCalled();

    linkCallbacks().onExit({ error: { displayMessage: "Bank is unavailable" } });
    expect(alert).toHaveBeenCalledWith("Connection cancelled", "Bank is unavailable");
  });

  it("goes back", () => {
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByLabelText("Go back"));
    expect(router().back).toHaveBeenCalled();
  });
});

describe("reconnecting a bank whose login expired", () => {
  beforeEach(() => useParams().mockReturnValue({ itemId: "7" }));

  it("says it is a reconnect", () => {
    renderScreen(<ConnectBank />);
    expect(screen.getByText("Reconnect Your Bank")).toBeTruthy();
    expect(screen.getByText("Sign in to your bank again")).toBeTruthy();
  });

  it("opens Link in update mode and re-syncs instead of exchanging a new token", async () => {
    apiMock.plaidApi.reconnectLinkToken.mockResolvedValue({ data: { link_token: "link-update-7" } });
    apiMock.plaidApi.reconnected.mockResolvedValue({ data: { status: "synced" } });
    renderScreen(<ConnectBank />);

    fireEvent.press(screen.getByText("Sign in to your bank again"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());
    expect(apiMock.plaidApi.reconnectLinkToken).toHaveBeenCalledWith(7);
    expect(apiMock.plaidApi.getLinkToken).not.toHaveBeenCalled();
    expect(createMock).toHaveBeenCalledWith({ token: "link-update-7" });

    await linkSucceeds();

    expect(apiMock.plaidApi.reconnected).toHaveBeenCalledWith(7);
    expect(apiMock.plaidApi.exchange).not.toHaveBeenCalled();
    expect(alert).toHaveBeenCalledWith("Reconnected", "Your bank is syncing again.");
    expect(router().replace).toHaveBeenCalledWith("/(tabs)");
  });

  it("reports when the re-sync still fails", async () => {
    apiMock.plaidApi.reconnectLinkToken.mockResolvedValue({ data: { link_token: "l" } });
    apiMock.plaidApi.reconnected.mockRejectedValue(apiError(502, "Bank provider error: still broken"));
    renderScreen(<ConnectBank />);
    fireEvent.press(screen.getByText("Sign in to your bank again"));
    await waitFor(() => expect(openMock).toHaveBeenCalled());

    await linkSucceeds();

    expect(alert).toHaveBeenCalledWith("Couldn't connect", "Bank provider error: still broken");
    expect(router().replace).not.toHaveBeenCalled();
  });
});
