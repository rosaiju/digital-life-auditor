import { formatShortDate, parseDateOnly, parseTimestamp, timeAgo } from "@/utils/dates";
import { isValidEmail, normalizeEmail, validateCredentials } from "@/utils/validation";
import { errorMessage } from "@/utils/alerts";

describe("dates", () => {
  it("reads a date-only string as that local calendar day (not UTC midnight)", () => {
    const d = parseDateOnly("2026-09-25");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 25]);
    expect(formatShortDate("2026-09-25")).toBe("Sep 25");
  });

  it("treats a timestamp without a zone as UTC, since the backend stores naive UTC", () => {
    expect(parseTimestamp("2026-09-25T02:00:00").toISOString()).toBe("2026-09-25T02:00:00.000Z");
    expect(parseTimestamp("2026-09-25T02:00:00.123456").toISOString()).toBe("2026-09-25T02:00:00.123Z");
    expect(parseTimestamp("2026-09-25T02:00:00Z").toISOString()).toBe("2026-09-25T02:00:00.000Z");
    expect(parseTimestamp("2026-09-25T02:00:00+02:00").toISOString()).toBe("2026-09-25T00:00:00.000Z");
  });

  it("describes elapsed time", () => {
    const now = Date.parse("2026-09-25T12:00:00Z");
    expect(timeAgo("2026-09-25T11:59:40", now)).toBe("just now");
    expect(timeAgo("2026-09-25T11:55:00", now)).toBe("5 min ago");
    expect(timeAgo("2026-09-25T09:00:00", now)).toBe("3 h ago");
    expect(timeAgo("2026-09-24T12:00:00", now)).toBe("1 day ago");
    expect(timeAgo("2026-09-20T12:00:00", now)).toBe("5 days ago");
    expect(timeAgo("2026-09-26T12:00:00", now)).toBe("just now"); // clock skew never goes negative
  });
});

describe("validation", () => {
  it("normalizes emails", () => {
    expect(normalizeEmail("  Demo@Example.COM ")).toBe("demo@example.com");
  });

  it("accepts and rejects email shapes", () => {
    expect(isValidEmail("a@b.co")).toBe(true);
    for (const bad of ["", "a", "a@b", "a b@c.com", "@b.com", "a@.com"]) expect(isValidEmail(bad)).toBe(false);
  });

  it("validates sign-in and sign-up credentials", () => {
    expect(validateCredentials("", "")).toBe("Please enter email and password");
    expect(validateCredentials("", "", { newAccount: true })).toBe("Please fill in all fields");
    expect(validateCredentials("nope", "password123")).toBe("Enter a valid email address");
    expect(validateCredentials("a@b.co", "short", { newAccount: true })).toBe("Password must be at least 8 characters");
    expect(validateCredentials("a@b.co", "short")).toBeNull(); // existing accounts may have any password
    expect(validateCredentials("a@b.co", "long-enough", { newAccount: true })).toBeNull();
  });
});

describe("errorMessage", () => {
  const axiosError = (status: number, data: unknown, code?: string) => ({ response: { status, data }, code });

  it("prefers the API's detail string", () => {
    expect(errorMessage(axiosError(401, { detail: "Incorrect email or password" }))).toBe("Incorrect email or password");
  });

  it("flattens FastAPI validation errors", () => {
    const detail = [{ msg: "Value error, bad email" }, { msg: "String should have at least 8 characters" }];
    expect(errorMessage(axiosError(422, { detail }))).toBe("bad email. String should have at least 8 characters");
  });

  it("explains network, timeout and server failures", () => {
    expect(errorMessage({ code: "ERR_NETWORK" })).toMatch(/Can't reach the server/);
    expect(errorMessage({ code: "ECONNABORTED" })).toMatch(/timed out/);
    expect(errorMessage(axiosError(500, "<html>oops</html>"))).toMatch(/server had a problem/);
  });

  it("falls back to the error message, then the default", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
    expect(errorMessage({}, "Fallback")).toBe("Fallback");
    expect(errorMessage(undefined)).toBe("Something went wrong");
  });
});
