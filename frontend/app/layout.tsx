import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PRL · Cognitive Core",
  description: "The AI's mind — a living particle brain of your reality.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
