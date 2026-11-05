import type { Metadata } from "next";
import { Familjen_Grotesk, Public_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const familjen = Familjen_Grotesk({ subsets: ["latin"], variable: "--font-familjen" });
const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-public" });

export const metadata: Metadata = {
  title: "EstateFlow",
  description: "Listings, WhatsApp leads and site visits in one place",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${familjen.variable} ${publicSans.variable}`}>
      <body className="min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
