import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import ChangePassword from "@/app/change-password";
import DeleteAccount from "@/app/delete-account";
import { queryClient } from "@/services/queryClient";
import { useAuthStore } from "@/store/auth";
import { apiMock, apiError, resetApiMock } from "../test-utils/apiMock";
import { alertSpy, pressAlertButton, renderScreen, resetApp, router, settle } from "../test-utils/render";

jest.mock("@/services/api", () => require("../test-utils/apiMock").apiMock);

let alert: jest.SpyInstance;
beforeEach(() => {
  resetApp();
  resetApiMock();
  alert = alertSpy();
});
afterEach(() => alert.mockRestore());

const type = (placeholder: string, value: string) => fireEvent.changeText(screen.getByPlaceholderText(placeholder), value);

describe("ChangePassword", () => {
  function fill(current = "old-password", next = "new-password-1", confirm = next) {
    type("Current password", current);
    type("New password", next);
    type("Confirm new password", confirm);
  }

  it("requires every field", () => {
    renderScreen(<ChangePassword />);
    type("Current password", "old-password");
    fireEvent.press(screen.getByText("Update password"));
    expect(screen.getByText("Please fill in every field")).toBeTruthy();
    expect(apiMock.authApi.changePassword).not.toHaveBeenCalled();
  });

  it("rejects a short or mismatched new password locally", () => {
    renderScreen(<ChangePassword />);
    fill("old-password", "short", "short");
    fireEvent.press(screen.getByText("Update password"));
    expect(screen.getByText("New password must be at least 8 characters")).toBeTruthy();

    fill("old-password", "new-password-1", "new-password-2");
    fireEvent.press(screen.getByText("Update password"));
    expect(screen.getByText("The new passwords don't match")).toBeTruthy();
    expect(apiMock.authApi.changePassword).not.toHaveBeenCalled();
  });

  it("updates the password and returns to settings", async () => {
    apiMock.authApi.changePassword.mockResolvedValue({});
    renderScreen(<ChangePassword />);
    fill();
    fireEvent.press(screen.getByText("Update password"));

    await waitFor(() => expect(router().back).toHaveBeenCalled());
    expect(apiMock.authApi.changePassword).toHaveBeenCalledWith("old-password", "new-password-1");
    expect(alert).toHaveBeenCalledWith("Password updated", expect.any(String));
  });

  it("shows the server's reason when the current password is wrong", async () => {
    apiMock.authApi.changePassword.mockRejectedValue(apiError(403, "Incorrect password"));
    renderScreen(<ChangePassword />);
    fill();
    fireEvent.press(screen.getByText("Update password"));

    expect(await screen.findByText("Incorrect password")).toBeTruthy();
    expect(router().back).not.toHaveBeenCalled();
  });
});

describe("DeleteAccount", () => {
  it("requires the password", () => {
    renderScreen(<DeleteAccount />);
    fireEvent.press(screen.getByText("Delete my account"));
    expect(screen.getByText("Please fill in every field")).toBeTruthy();
    expect(apiMock.authApi.deleteAccount).not.toHaveBeenCalled();
  });

  it("asks for a final confirmation before deleting anything", async () => {
    apiMock.authApi.deleteAccount.mockResolvedValue({});
    renderScreen(<DeleteAccount />);
    type("Your password", "right-password");
    fireEvent.press(screen.getByText("Delete my account"));

    expect(alert).toHaveBeenCalledWith("Delete account?", expect.stringContaining("can't be undone"), expect.any(Array));
    expect(apiMock.authApi.deleteAccount).not.toHaveBeenCalled();
    await settle();
  });

  it("deletes the account after confirmation, then signs out and drops all cached data", async () => {
    apiMock.authApi.deleteAccount.mockResolvedValue({});
    queryClient.setQueryData(["subscriptions", "active"], [{ id: 1 }]);
    renderScreen(<DeleteAccount />);
    type("Your password", "right-password");
    fireEvent.press(screen.getByText("Delete my account"));
    await pressAlertButton(alert, "Delete forever");

    await waitFor(() => expect(useAuthStore.getState().token).toBeNull());
    expect(apiMock.authApi.deleteAccount).toHaveBeenCalledWith("right-password");
    expect(queryClient.getQueryData(["subscriptions", "active"])).toBeUndefined();
  });

  it("stays signed in and explains when the password is wrong", async () => {
    apiMock.authApi.deleteAccount.mockRejectedValue(apiError(403, "Incorrect password"));
    renderScreen(<DeleteAccount />);
    type("Your password", "wrong");
    fireEvent.press(screen.getByText("Delete my account"));
    await pressAlertButton(alert, "Delete forever");

    expect(await screen.findByText("Incorrect password")).toBeTruthy();
    expect(useAuthStore.getState().token).toBe("test-token");
  });
});
