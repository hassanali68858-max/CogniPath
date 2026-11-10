"use client";

import { createContext, useContext, useEffect, useState } from "react";

const KEY = "cognipath.userId";
export const DEFAULT_USER = "student001";

type Ctx = { userId: string; setUserId: (id: string) => void };
const UserContext = createContext<Ctx>({ userId: DEFAULT_USER, setUserId: () => {} });

/** Which student we are working with. Remembered in this browser only (there is no login yet). */
export function UserProvider({ children }: { children: React.ReactNode }) {
  const [userId, setUserIdState] = useState(DEFAULT_USER);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(KEY);
      if (saved) setUserIdState(saved);
    } catch {
      /* storage blocked: keep the default */
    }
  }, []);

  const setUserId = (id: string) => {
    setUserIdState(id);
    try {
      window.localStorage.setItem(KEY, id);
    } catch {
      /* ignore */
    }
  };

  return <UserContext.Provider value={{ userId, setUserId }}>{children}</UserContext.Provider>;
}

export const useUser = () => useContext(UserContext);
