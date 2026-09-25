export const MIN_PASSWORD_LENGTH = 8;

/** Emails are case-insensitive and keyboards like to append a space. */
export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
}

/** Returns an error message, or null when the credentials look acceptable. */
export function validateCredentials(email: string, password: string, { newAccount = false } = {}): string | null {
  if (!email || !password) return newAccount ? "Please fill in all fields" : "Please enter email and password";
  if (!isValidEmail(email)) return "Enter a valid email address";
  if (newAccount && password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
  }
  return null;
}
