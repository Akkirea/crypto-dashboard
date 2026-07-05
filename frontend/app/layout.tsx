import "./globals.css";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: {
    default: "EA Crypto Dashboard",
    template: "%s | EA Crypto"
  },
  description: "Live crypto market intelligence, analytics, and paper simulation dashboard",
  applicationName: "EA Crypto",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icon.svg",
    shortcut: "/icon.svg",
    apple: "/icon.svg"
  },
  appleWebApp: {
    capable: true,
    title: "EA Crypto",
    statusBarStyle: "black-translucent"
  }
};

export const viewport: Viewport = {
  themeColor: "#0b0b10"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
