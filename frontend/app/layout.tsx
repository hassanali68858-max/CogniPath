import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { StatusProvider } from "@/components/StatusProvider";
import { ToastProvider } from "@/components/Toast";
import { UserProvider } from "@/components/UserProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "CogniPath Planner",
  description: "Your study, career and social week, balanced by the CogniPath Planner Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={GeistSans.variable}>
      <body>
        <UserProvider>
          <StatusProvider>
            <ToastProvider>
              <AppShell>{children}</AppShell>
            </ToastProvider>
          </StatusProvider>
        </UserProvider>
      </body>
    </html>
  );
}
