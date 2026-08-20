import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host");
  const protocol = requestHeaders.get("x-forwarded-proto") ?? "https";
  const metadataBase = new URL(`${protocol}://${host ?? "localhost"}`);

  return {
    metadataBase,
    title: "職缺雷達｜技能需求與市場洞察",
    description:
      "從公開職缺資料探索技能需求、薪資、應徵競爭、公司、地點與經驗層級。",
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
    },
    openGraph: {
      title: "JOB RADAR｜看懂技能市場，準備下一步。",
      description:
        "探索技能需求、薪資、應徵競爭、公司、地點與經驗層級。",
      type: "website",
      images: [{ url: "/og.png", width: 1730, height: 909 }],
    },
    twitter: {
      card: "summary_large_image",
      title: "JOB RADAR｜看懂技能市場，準備下一步。",
      description:
        "探索技能需求、薪資、應徵競爭、公司、地點與經驗層級。",
      images: ["/og.png"],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
