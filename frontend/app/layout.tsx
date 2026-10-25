import type { Metadata } from "next";

import { Nav } from "@/components/Nav";
import { UserProvider } from "@/components/UserProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "CogniPath Planner",
  description: "Test UI for the CogniPath Planner Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <UserProvider>
          <Nav />
          <main className="page">{children}</main>
        </UserProvider>
      </body>
    </html>
  );
}
