import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI HR Intelligence Platform",
  description: "Enterprise AI-Powered Recruitment, ATS & Workforce Intelligence Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
