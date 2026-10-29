import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Second Look",
  description: "The right patient facts for every doctor's task, and a warning when the record is wrong.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
