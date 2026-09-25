import { PasswordForm } from "@/components/PasswordForm";
import { authApi } from "@/services/api";
import { errorMessage } from "@/utils/alerts";
import { useAuthStore } from "@/store/auth";

export default function DeleteAccount() {
  const logout = useAuthStore((s) => s.logout);
  return (
    <PasswordForm
      title="Delete account"
      description="This permanently deletes your account, your subscriptions, insights and saved transactions, and disconnects every linked bank. It can't be undone."
      fields={[{ key: "password", placeholder: "Your password", autoComplete: "current-password" }]}
      submitLabel="Delete my account"
      destructive
      confirmation={{
        title: "Delete account?",
        message: "Everything will be permanently erased and your banks disconnected. This can't be undone.",
        confirmLabel: "Delete forever",
      }}
      onSubmit={async (v) => {
        await authApi.deleteAccount(v.password);
        await logout(); // clears the session and cached data; the auth guard returns to sign-in
      }}
      errorMessage={errorMessage}
    />
  );
}
