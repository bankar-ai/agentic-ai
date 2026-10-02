import { createContext, useContext, useState, type ReactNode } from "react";

/** A logged-in `enterprise-rag-platform` session, held in memory only (AGT-017) -- never
 * written to localStorage/sessionStorage, so it's lost on refresh, matching the Gradio demo's
 * own never-persisted-to-disk stance (app/ui/app.py's `login()`).
 */
export interface Session {
  accessToken: string;
  csrfToken: string;
  email: string;
}

interface SessionContextValue {
  session: Session | null;
  login: (session: Session) => void;
  logout: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);

  const value: SessionContextValue = {
    session,
    login: setSession,
    logout: () => setSession(null),
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
