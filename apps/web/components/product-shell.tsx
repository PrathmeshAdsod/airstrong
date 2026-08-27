"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { dashboardNavigation } from "@/lib/navigation";

import { Brand } from "./brand";

type ProductShellProps = {
  children: ReactNode;
};

export function ProductShell({ children }: ProductShellProps) {
  const pathname = usePathname();

  return (
    <div className="product-shell">
      <header className="product-nav">
        <Brand />
        <nav aria-label="Airstrong product">
          {dashboardNavigation.map((item) => {
            const active = pathname === item.href;

            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={active ? "is-active" : undefined}
                href={item.href}
                key={item.label}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div
          className="world-badge"
          aria-label="Aliens Airline simulation world"
        >
          <span className="world-badge__dot" aria-hidden="true" />
          <strong>Aliens Airline</strong>
          <span aria-hidden="true">·</span>
          <span>Simulation</span>
        </div>
      </header>
      <main className="product-main">{children}</main>
    </div>
  );
}
