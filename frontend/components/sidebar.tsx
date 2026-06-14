"use client";

import Link from "next/link";

import { usePathname } from "next/navigation";

export function Sidebar() {
  const pathname = usePathname();

  const links = [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { href: "/live", label: "Workflows", icon: "account_tree" },
    { href: "/history", label: "Intelligence", icon: "history" },
    { href: "/schedule", label: "Scheduling", icon: "event" },
  ];

  return (
    <aside className="flex flex-col h-screen fixed left-0 top-0 w-64 bg-surface-container-low dark:bg-surface-container-low border-r border-outline-variant transition-all duration-200 ease-in-out z-50">
      <div className="px-lg py-xl">
        <h1 className="font-headline-sm text-headline-sm font-bold text-primary dark:text-primary-fixed-dim">HERO AWPIS</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">Automated Website Performance Improvement System</p>
      </div>
      <nav className="flex-grow px-sm space-y-1">
        {links.map((link) => {
          const isActive = pathname?.startsWith(link.href);

          if (isActive) {
            return (
              <Link
                key={link.href}
                href={link.href}
                className="flex items-center gap-md px-md py-sm text-primary dark:text-primary-fixed-dim font-bold border-r-2 border-primary hover:bg-surface-container-high transition-all duration-200 font-body-md text-body-md"
              >
                <span className="material-symbols-outlined transition-transform duration-200">{link.icon}</span>
                <span>{link.label}</span>
              </Link>
            );
          } else {
            return (
              <Link
                key={link.href}
                href={link.href}
                className="flex items-center gap-md px-md py-sm text-on-surface-variant hover:bg-surface-container-high hover:text-primary transition-all duration-200 font-body-md text-body-md group"
              >
                <span className="material-symbols-outlined group-hover:scale-110 transition-transform">{link.icon}</span>
                <span>{link.label}</span>
              </Link>
            );
          }
        })}
      </nav>
      <div className="px-sm pb-xl space-y-1 border-t border-outline-variant pt-lg">
        <span className="flex items-center gap-md px-md py-sm text-outline font-body-md text-body-md cursor-not-allowed">
          <span className="material-symbols-outlined">settings</span>
          <span>Settings</span>
        </span>
        <span className="flex items-center gap-md px-md py-sm text-outline font-body-md text-body-md cursor-not-allowed">
          <span className="material-symbols-outlined">help</span>
          <span>Support</span>
        </span>
        <div className="mt-lg px-md flex items-center gap-md">
          <div className="w-8 h-8 rounded-full border border-outline-variant hover:border-primary transition-colors cursor-pointer bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-xs">
            AU
          </div>
          <div>
            <p className="font-label-md text-label-md font-bold">Admin User</p>
            <p className="text-[10px] text-on-surface-variant uppercase tracking-wider">Enterprise Tier</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
