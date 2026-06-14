import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AWPIS Dashboard",
  description: "Autonomous Web Performance Intelligence System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="light scroll-smooth">
      <head>
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
      </head>
      <body className={`${inter.className} bg-background text-on-surface antialiased flex min-h-screen overflow-x-hidden`}>
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="flex justify-between items-center w-full px-lg h-16 bg-surface-container-lowest dark:bg-surface-container-lowest border-b border-outline-variant fixed top-0 right-0 z-40 transition-all" style={{ width: 'calc(100% - 16rem)' }}>
            <div className="flex items-center gap-xl flex-1">
              <div className="relative w-64">
                <span className="material-symbols-outlined absolute left-sm top-1/2 -translate-y-1/2 text-outline">search</span>
                <input className="w-full bg-surface-container-low border-none rounded-lg pl-xl py-xs font-body-md text-body-md focus:ring-1 focus:ring-primary transition-all duration-200" placeholder="Search operations..." type="text" />
              </div>
              <nav className="flex gap-lg">
                <span className="text-primary dark:text-primary-fixed-dim font-bold border-b-2 border-primary pb-1 font-body-md text-body-md cursor-not-allowed">Health Overview</span>
                <span className="text-on-surface-variant font-body-md text-body-md cursor-not-allowed">Audit Logs</span>
              </nav>
            </div>
            <div className="flex items-center gap-lg">
              <div className="flex items-center gap-sm pr-lg border-r border-outline-variant">
                <button className="flex items-center gap-xs text-on-surface-variant font-body-md text-body-md cursor-not-allowed" disabled>
                  <span className="material-symbols-outlined">apps</span>
                  <span>System Status</span>
                </button>
              </div>
              <div className="flex items-center gap-md">
                <button className="material-symbols-outlined text-on-surface-variant cursor-not-allowed" disabled>notifications</button>
                <button className="bg-surface-container-high text-outline px-md py-xs rounded-lg font-body-md text-body-md font-bold cursor-not-allowed" disabled>Deploy Plan</button>
              </div>
            </div>
          </header>
          <main className="flex-1 ml-64 mt-16 p-xxl min-h-[calc(100vh-64px)] overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
