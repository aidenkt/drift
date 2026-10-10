import { ClerkProvider, SignIn, UserButton, useAuth } from "@clerk/react";
import type { ReactNode } from "react";

const KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

/** Clerk sign-in in front of the app. Without a key (local dev) the app runs signed out. */
export default function AuthGate({ children }: { children: ReactNode }) {
  if (!KEY) return <>{children}</>;
  return (
    <ClerkProvider publishableKey={KEY}>
      <Gate>{children}</Gate>
    </ClerkProvider>
  );
}

function Gate({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) return null;
  if (!isSignedIn)
    return (
      <div className="signin">
        <span className="wordmark">Since</span>
        <SignIn routing="hash" />
      </div>
    );
  return <>{children}</>;
}

/** Account menu for the top bar; renders nothing without Clerk. */
export function Account() {
  return KEY ? <UserButton /> : null;
}
