import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { persianDigits } from "@/lib/format";

export const metadata: Metadata = {
  title: "تصویر رسید | هشتی",
  robots: { index: false, follow: false },
};

export default async function ReceiptPage({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ viewer?: string }>;
}) {
  const { id } = await params;
  const { viewer } = await searchParams;
  if (!/^[1-9]\d*$/.test(id)) notFound();
  const admin = viewer === "admin";
  const image = `/api/${admin ? "admin" : "me"}/payments/${id}/receipt`;

  return <main className="receipt-viewer">
    <div className="receipt-viewer-bar">
      <div><span>هشتی · تصویر واریز</span><h1>رسید شمارهٔ {persianDigits(id)}</h1></div>
      <Link href={admin ? "/panel/payments" : "/account#receipts"}>بازگشت به {admin ? "بررسی رسیدها" : "حساب من"} ←</Link>
    </div>
    <div className="receipt-viewer-image">
      <img src={image} alt={`تصویر رسید شمارهٔ ${persianDigits(id)}`} />
    </div>
  </main>;
}
