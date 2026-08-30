import type { Metadata } from "next";
import { Inter, Noto_Sans_Bengali, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { LocaleProvider } from "@/components/locale-provider";
import { SiteChrome } from "@/components/site-chrome";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// Bengali glyphs are missing from Inter, so Bangla would fall back to a system
// font and look inconsistent with the rest of the page.
const notoBengali = Noto_Sans_Bengali({
  subsets: ["bengali"],
  variable: "--font-bengali",
  display: "swap",
});

// Serif headlines carry the editorial character; the body stays in a neutral sans.
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "তথ্য যাচাই — Evidence Check",
    template: "%s · তথ্য যাচাই",
  },
  description:
    "Submit a claim, article, image, or video and see what the available evidence establishes — with sources you can check yourself. সত্য জানুন, গুজব থামান।",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-32x32.png", type: "image/png", sizes: "32x32" },
      { url: "/favicon-16x16.png", type: "image/png", sizes: "16x16" },
    ],
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "তথ্য যাচাই — Evidence Check",
    description: "সত্য জানুন, গুজব থামান। Evidence-backed verification.",
    images: ["/logo.png"],
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${sourceSerif.variable} ${notoBengali.variable}`}>
      <body className="min-h-screen flex flex-col">
        <LocaleProvider>
          <QueryProvider>
            <SiteChrome>{children}</SiteChrome>
          </QueryProvider>
        </LocaleProvider>

      </body>
    </html>
  );
}
