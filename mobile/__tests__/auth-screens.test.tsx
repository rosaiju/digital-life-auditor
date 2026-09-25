import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import Login from "@/app/(auth)/login";
import Register from "@/app/(auth)/register";
import { useAuthStore } from "@/store/auth";
import { apiMock, apiError, resetApiMock } from "../test-utils/apiMock";
import { alertSpy, renderScreen, resetApp } from "../test-utils/render";

jest.mock("@/services/api", () => require("../test-utils/apiMock").apiMock);

let alert: jest.SpyInstance;
beforeEach(() => {
  resetApp({ signedIn: false });
  resetApiMock();
  alert = alertSpy();
});
afterEach(() => alert.mockRestore());

const type = (placeholder: string | RegExp, value: string) =>
  fireEvent.changeText(screen.getByPlaceholderText(placeholder), value);
// "Create Account" is both the heading and the button; the button comes last.
const pressCreateAccount = () => fireEvent.press(screen.getAllByText("Create Account").slice(-1)[0]);

describe("Login", () => {
  it("asks for both fields before calling the API", () => {
    renderScreen(<Login />);
    fireEvent.press(screen.getByText("Sign In"));
    expect(alert).toHaveBeenCalledWith("Check your details", "Please enter email and password");
    expect(apiMock.authApi.login).not.toHaveBeenCalled();
  });

  it("rejects a malformed email", () => {
    renderScreen(<Login />);
    type("Email", "not-an-email");
    type("Password", "whatever");
    fireEvent.press(screen.getByText("Sign In"));
    expect(alert).toHaveBeenCalledWith("Check your details", "Enter a valid email address");
    expect(apiMock.authApi.login).not.toHaveBeenCalled();
  });

  it("trims and lowercases the email, then stores the token", async () => {
    apiMock.authApi.login.mockResolvedValue({ data: { access_token: "jwt-1" } });
    renderScreen(<Login />);
    type("Email", "  Demo@Example.com ");
    type("Password", "demo-password");
    fireEvent.press(screen.getByText("Sign In"));

    await waitFor(() => expect(useAuthStore.getState().token).toBe("jwt-1"));
    expect(apiMock.authApi.login).toHaveBeenCalledWith("demo@example.com", "demo-password");
  });

  it("shows the server's message when sign-in fails and stays signed out", async () => {
    apiMock.authApi.login.mockRejectedValue(apiError(401, "Incorrect email or password"));
    renderScreen(<Login />);
    type("Email", "a@b.co");
    type("Password", "wrong-password");
    fireEvent.press(screen.getByText("Sign In"));

    await waitFor(() => expect(alert).toHaveBeenCalledWith("Login failed", "Incorrect email or password"));
    expect(useAuthStore.getState().token).toBeNull();
    expect(screen.getByText("Sign In")).toBeTruthy(); // button is usable again
  });

  it("explains rate limiting", async () => {
    apiMock.authApi.login.mockRejectedValue(apiError(429, "Too many attempts, try again shortly"));
    renderScreen(<Login />);
    type("Email", "a@b.co");
    type("Password", "x");
    fireEvent.press(screen.getByText("Sign In"));
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Login failed", "Too many attempts, try again shortly"));
  });

  it("submits from the keyboard Go key and ignores repeat submits while loading", async () => {
    let resolve: (v: unknown) => void = () => {};
    apiMock.authApi.login.mockReturnValue(new Promise((r) => (resolve = r)));
    renderScreen(<Login />);
    type("Email", "a@b.co");
    type("Password", "password1");

    fireEvent(screen.getByPlaceholderText("Password"), "submitEditing");
    fireEvent(screen.getByPlaceholderText("Password"), "submitEditing");

    expect(apiMock.authApi.login).toHaveBeenCalledTimes(1);
    resolve({ data: { access_token: "t" } });
    await waitFor(() => expect(useAuthStore.getState().token).toBe("t"));
  });
});

describe("Register", () => {
  it("enforces the minimum password length locally", () => {
    renderScreen(<Register />);
    type("Email", "new@example.com");
    type(/^Password/, "short");
    pressCreateAccount();
    expect(alert).toHaveBeenCalledWith("Check your details", "Password must be at least 8 characters");
    expect(apiMock.authApi.register).not.toHaveBeenCalled();
  });

  it("registers with a normalized email and signs in", async () => {
    apiMock.authApi.register.mockResolvedValue({ data: { access_token: "jwt-2" } });
    renderScreen(<Register />);
    type("Email", " New@Example.com");
    type(/^Password/, "long-enough-1");
    pressCreateAccount();

    await waitFor(() => expect(useAuthStore.getState().token).toBe("jwt-2"));
    expect(apiMock.authApi.register).toHaveBeenCalledWith("new@example.com", "long-enough-1");
  });

  it("reports an already-registered email", async () => {
    apiMock.authApi.register.mockRejectedValue(apiError(400, "Email already registered"));
    renderScreen(<Register />);
    type("Email", "taken@example.com");
    type(/^Password/, "long-enough-1");
    pressCreateAccount();
    await waitFor(() => expect(alert).toHaveBeenCalledWith("Registration failed", "Email already registered"));
  });
});
