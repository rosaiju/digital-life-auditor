import { useRouter } from "expo-router";
import { PasswordForm } from "@/components/PasswordForm";
import { authApi } from "@/services/api";
import { errorMessage, showAlert } from "@/utils/alerts";
import { MIN_PASSWORD_LENGTH } from "@/utils/validation";

export default function ChangePassword() {
  const router = useRouter();
  return (
    <PasswordForm
      title="Change password"
      description="Enter your current password, then choose a new one."
      fields={[
        { key: "current", placeholder: "Current password", autoComplete: "current-password" },
        { key: "next", placeholder: "New password", autoComplete: "new-password" },
        { key: "confirm", placeholder: "Confirm new password", autoComplete: "new-password" },
      ]}
      submitLabel="Update password"
      validate={(v) =>
        v.next.length < MIN_PASSWORD_LENGTH
          ? `New password must be at least ${MIN_PASSWORD_LENGTH} characters`
          : v.next !== v.confirm
          ? "The new passwords don't match"
          : null
      }
      onSubmit={async (v) => {
        await authApi.changePassword(v.current, v.next);
        showAlert("Password updated", "Use your new password next time you sign in.");
        router.back();
      }}
      errorMessage={errorMessage}
    />
  );
}
