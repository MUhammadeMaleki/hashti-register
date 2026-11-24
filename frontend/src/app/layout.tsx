import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const anjoman = localFont({
  src: "../fonts/anjoman/04 - Anjoman Variable/Variable WebFont/AnjomanMaxVF.woff2",
  weight: "100 900",
  display: "swap",
});

export const metadata: Metadata = {
  title: "هشتی | سامانه مدیریت رویداد",
  description: "سامانه مدیریت رویدادها، مخاطبان و کیف پول هشتی",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fa" dir="rtl" className={anjoman.className}><body>{children}</body></html>;
}
