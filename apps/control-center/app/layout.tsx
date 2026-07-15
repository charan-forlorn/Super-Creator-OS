import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SCOS Agent Operations Cockpit",
  description:
    "Local-first cockpit for an operator to review agent work, approvals, and evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="th" className="dark">
      <body className="min-h-screen bg-canvas text-ink antialiased">
        {children}
      </body>
    </html>
  );
}
