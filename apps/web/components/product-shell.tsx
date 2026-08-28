"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { dashboardNavigation } from "@/lib/navigation";

import { Brand } from "./brand";
import { useWorld, WorldProvider } from "./world-provider";

type ProductShellProps = {
  children: ReactNode;
};

function ProductFrame({ children }: ProductShellProps) {
  const pathname = usePathname();
  const { streamState, world } = useWorld();

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
          aria-label={`${world?.displayName ?? "Aliens Airline"} simulation world, event stream ${streamState}`}
        >
          <span
            className={`world-badge__dot world-badge__dot--${streamState}`}
            aria-hidden="true"
          />
          <strong>{world?.displayName ?? "Aliens Airline"}</strong>
          <span aria-hidden="true">·</span>
          <span>Simulation</span>
        </div>
      </header>
      <main className="product-main">{children}</main>
    </div>
  );
}

export function ProductShell({ children }: ProductShellProps) {
  return (
    <WorldProvider>
      <ProductFrame>{children}</ProductFrame>
    </WorldProvider>
  );
}
