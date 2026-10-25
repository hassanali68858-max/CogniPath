"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useUser } from "./UserProvider";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/profile", label: "1 · Profile" },
  { href: "/proposals", label: "2 · Proposals" },
  { href: "/plan", label: "3 · Plan" },
];

export function Nav() {
  const path = usePathname();
  const { userId } = useUser();
  return (
    <header className="nav">
      <div className="nav-inner">
        <Link href="/" className="brand">
          CogniPath <span className="muted">planner test UI</span>
        </Link>
        <nav>
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>
              {l.label}
            </Link>
          ))}
        </nav>
        <span className="user-chip" title="Change it on the Home page">
          {userId}
        </span>
      </div>
    </header>
  );
}
