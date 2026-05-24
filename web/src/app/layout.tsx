import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Toaster } from "sonner";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "helium-prospector",
  description: "Lead-Generation & CRM für Helium-Direktbeteiligung",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className="dark">
      <body className={`${inter.variable} font-sans antialiased min-h-svh`}>
        {children}
        <Toaster
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: "var(--popover)",
              color: "var(--popover-foreground)",
              border: "1px solid var(--border)",
            },
          }}
        />
      </body>
    </html>
  );
}
