"use client";

/**
 * Component: NavigationMenu
 * Author / Library: shadcn/ui (adapted from 21st.dev community/components/s/navigation-menu)
 * Source URL: https://21st.dev/s/navigation-menu
 *
 * Re-themed to Ledgerlight design tokens:
 * - Ink text: #16181D
 * - Primary accent: #1F4D3F
 * - Border: #E2DDD2
 * - No gradient hero or glowing orbs.
 */

import React from "react";
import Link from "next/link";

interface NavItem {
  label: string;
  href: string;
  active?: boolean;
}

interface NavigationMenuProps {
  brandName?: string;
  items?: NavItem[];
  rightElement?: React.ReactNode;
}

export function NavigationMenu({
  brandName = "Ledgerlight",
  items = [
    { label: "Overview", href: "/" },
    { label: "Assessments", href: "/onboarding" },
    { label: "Question Bank", href: "/admin" },
  ],
  rightElement,
}: NavigationMenuProps) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-[#E2DDD2] bg-[#F6F3EC]/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2 group">
            <span className="h-6 w-2 bg-[#1F4D3F] rounded-xs" />
            <span className="font-serif text-xl font-bold tracking-tight text-[#16181D]">
              {brandName}
            </span>
            <span className="rounded bg-[#E8F0EC] px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[#1F4D3F]">
              AUDIT v1.0
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-[#5F6470]">
            {items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`transition-colors hover:text-[#16181D] ${
                  item.active ? "text-[#1F4D3F] font-semibold" : ""
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>

        {rightElement && <div className="flex items-center gap-3">{rightElement}</div>}
      </div>
    </header>
  );
}
