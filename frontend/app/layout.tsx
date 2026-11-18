import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { StatusProvider } from "@/components/StatusProvider";
import { ToastProvider } from "@/components/Toast";
import { UserProvider } from "@/components/UserProvider";
import { Bricolage_Grotesque, Figtree } from "next/font/google";

import "./globals.css";

const figtree = Figtree({
  subsets: ["latin"],
  variable: "--font-figtree",
});

const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
});
export const metadata: Metadata = {
  title: "CogniPath Planner",
  description: "Your study, career and social week, balanced by the CogniPath Planner Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
  lang="en"
  className={`${GeistSans.variable} ${figtree.variable} ${bricolage.variable}`}
>
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
