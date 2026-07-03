import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SCOS Agent Control Center",
  description:
    "Local-first control center for coordinating ChatGPT, Claude Code, Codex, and Hermes during SCOS stage-gated development.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-canvas text-ink antialiased">
        {children}
      </body>
    </html>
  );
}
