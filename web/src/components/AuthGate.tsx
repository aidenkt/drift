import { ClerkProvider, SignIn, UserButton, useAuth } from "@clerk/react";
import type { ReactNode } from "react";
import Wordmark from "./Wordmark";

const KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

/** Clerk themed to the Since palette (see styles.css :root). Magenta stays reserved for STALE. */
const appearance = {
  variables: {
    colorPrimary: "#0e0e0e",
    colorPrimaryForeground: "#ffffff",
    colorForeground: "#0e0e0e",
    colorMutedForeground: "#6b6b6b",
    colorBackground: "#ffffff",
    colorMuted: "#f4f4f4",
    colorInput: "#ffffff",
    colorInputForeground: "#0e0e0e",
    colorBorder: "#e4e4e4",
    colorRing: "#1f47b8",
    colorNeutral: "#0e0e0e",
    colorDanger: "#a3134a",
    colorSuccess: "#0f8b8d",
    fontFamily: '-apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif',
    fontFamilyMono: 'ui-monospace, "SF Mono", Menlo, monospace',
    borderRadius: "3px",
  },
};

/** Clerk sign-in in front of the app. Without a key (local dev) the app runs signed out. */
export default function AuthGate({ children }: { children: ReactNode }) {
  if (!KEY) return <>{children}</>;
  return (
    <ClerkProvider publishableKey={KEY} appearance={appearance}>
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
        <Wordmark />
        <SignIn routing="hash" />
      </div>
    );
  return <>{children}</>;
}

/** Account menu for the top bar; renders nothing without Clerk. */
export function Account() {
  return KEY ? <UserButton /> : null;
}
