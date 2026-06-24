import type { Metadata } from "next";
import { Geist, Geist_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import CursorRing from "@/components/CursorRing";
import { ThemeProvider } from "@/components/ThemeProvider";
import QueryProvider from "@/components/QueryProvider";
import { ToastProvider } from "@/components/ToastProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const plusJakarta = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "MasterSAT",
  description: "MasterSAT - Advanced SAT Preparation Platform",
  icons: {
    icon: "/images/logo.png",
    apple: "/images/logo.png",
  },
};

import Script from "next/script";
import "katex/dist/katex.min.css";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head />
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${plusJakarta.variable} antialiased`}
      >
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <QueryProvider>
            <ToastProvider>
              <CursorRing />
              {children}
            </ToastProvider>
          </QueryProvider>
        </ThemeProvider>
        <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" />
      </body>
    </html>
  );
}
