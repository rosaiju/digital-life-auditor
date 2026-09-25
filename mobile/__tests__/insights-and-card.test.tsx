import { Linking } from "react-native";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import Insights from "@/app/(tabs)/insights";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { apiMock, apiError, resetApiMock } from "../test-utils/apiMock";
import { alertSpy, pressAlertButton, renderScreen, resetApp } from "../test-utils/render";

jest.mock("@/services/api", () => require("../test-utils/apiMock").apiMock);

const insights = (over: Record<string, unknown> = {}) => ({
  summary: "You spend $28.48 a month on 2 subscriptions.",
  insights: [{ type: "savings", title: "Bundle streaming", detail: "Two services overlap.", potential_savings: 10.99 }],
  category_breakdown: { Entertainment: 26.48, Productivity: 2 },
  top_opportunity: "Cancel Spotify to save $131.88 a year",
  monthly_total: 28.48,
  yearly_total: 341.76,
  subscription_count: 2,
  source: "rules",
  generated_at: "2026-09-25T02:30:00",
  ...over,
});

let alert: jest.SpyInstance;
beforeEach(() => {
  resetApp();
  resetApiMock();
  alert = alertSpy();
});
afterEach(() => alert.mockRestore());

describe("Insights", () => {
  it("shows generated insights", async () => {
    apiMock.insightsApi.get.mockResolvedValue({ data: insights() });
    renderScreen(<Insights />);

    expect(await screen.findByText("You spend $28.48 a month on 2 subscriptions.")).toBeTruthy();
    expect(screen.getByText("Bundle streaming")).toBeTruthy();
    expect(screen.getByText("Cancel Spotify to save $131.88 a year")).toBeTruthy();
    expect(screen.getByText("$341.76")).toBeTruthy();
    expect(screen.getByText(/rule-based analysis/)).toBeTruthy();
  });

  it("offers to generate insights when there are none yet", async () => {
    apiMock.insightsApi.get.mockResolvedValue({ data: { message: "No insights yet." } });
    renderScreen(<Insights />);
    expect(await screen.findByText("No insights yet")).toBeTruthy();
  });

  it("does not pretend there are no insights when loading failed", async () => {
    apiMock.insightsApi.get.mockRejectedValue({ code: "ERR_NETWORK" });
    renderScreen(<Insights />);

    expect(await screen.findByText("Couldn't load insights")).toBeTruthy();
    expect(screen.queryByText("No insights yet")).toBeNull();

    apiMock.insightsApi.get.mockResolvedValue({ data: insights() });
    fireEvent.press(screen.getByText("Try again"));
    expect(await screen.findByText("Bundle streaming")).toBeTruthy();
  });

  it("generates insights on demand and shows them", async () => {
    apiMock.insightsApi.get.mockResolvedValue({ data: { message: "No insights yet." } });
    apiMock.insightsApi.generate.mockResolvedValue({ data: insights() });
    renderScreen(<Insights />);
    await screen.findByText("No insights yet");

    apiMock.insightsApi.get.mockResolvedValue({ data: insights() });
    fireEvent.press(screen.getByText("✦ Generate"));

    expect(await screen.findByText("Bundle streaming")).toBeTruthy();
    expect(apiMock.insightsApi.generate).toHaveBeenCalledTimes(1);
  });

  it("reports a failed generation", async () => {
    apiMock.insightsApi.get.mockResolvedValue({ data: { message: "No insights yet." } });
    apiMock.insightsApi.generate.mockRejectedValue(apiError(500, "boom"));
    renderScreen(<Insights />);
    fireEvent.press(await screen.findByText("✦ Generate"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Couldn't generate insights", "boom"));
  });
});

describe("SubscriptionCard", () => {
  const subscription = {
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
    cancel_url: "https://www.netflix.com/cancelplan",
    monthly_cost: 15.49,
  };

  it("shows the price, cost per month and next charge on the right calendar day", () => {
    render(<SubscriptionCard subscription={subscription} onDismiss={() => {}} />);
    expect(screen.getByText("Netflix")).toBeTruthy();
    expect(screen.getByText("$15.49")).toBeTruthy();
    expect(screen.getByText("/mo")).toBeTruthy();
    expect(screen.getByText("Next: Oct 1")).toBeTruthy();
  });

  it("falls back to the merchant name and hides missing optional parts", () => {
    render(
      <SubscriptionCard
        subscription={{ ...subscription, display_name: null, category: null, next_charge_date: null, cancel_url: null }}
        onDismiss={() => {}}
      />
    );
    expect(screen.getByText("netflix")).toBeTruthy();
    expect(screen.queryByText(/Next:/)).toBeNull();
    expect(screen.queryByText("Cancel plan")).toBeNull();
  });

  it("opens the cancellation page", () => {
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    render(<SubscriptionCard subscription={subscription} onDismiss={() => {}} />);
    fireEvent.press(screen.getByText("Cancel plan"));
    expect(open).toHaveBeenCalledWith("https://www.netflix.com/cancelplan");
    open.mockRestore();
  });

  it("tells the user when the cancellation page cannot be opened", async () => {
    const open = jest.spyOn(Linking, "openURL").mockRejectedValue(new Error("no browser"));
    render(<SubscriptionCard subscription={subscription} onDismiss={() => {}} />);
    fireEvent.press(screen.getByText("Cancel plan"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Couldn't open link", subscription.cancel_url));
    open.mockRestore();
  });

  it("asks before dismissing", async () => {
    const onDismiss = jest.fn();
    render(<SubscriptionCard subscription={subscription} onDismiss={onDismiss} />);
    fireEvent.press(screen.getByLabelText("Dismiss Netflix"));
    expect(onDismiss).not.toHaveBeenCalled();
    await pressAlertButton(alert, "Dismiss");
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
