"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Today } from "@/components/today";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { reportsApi, type Dashboard } from "@/lib/reports";

export default function PanelPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    reportsApi.dashboard().then((result) => { if (active) setData(result); })
      .catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, []);
  return <AppShell kind="user"><div className="dashboard-overview">
    <section className="dashboard-intro" aria-labelledby="dashboard-title">
      <div><span className="dashboard-eyebrow">داشبورد هشتی <span aria-hidden="true">●</span> در یک نگاه</span>
        <h2 id="dashboard-title">نبض هشتی، همین‌جا.</h2>
        <p>هشتی‌ها، هشتی‌نشین‌ها و کارهای در انتظار، کنار هم.</p>
      </div>
      <div className="dashboard-date"><span>امروز</span><Today /></div>
    </section>
    {error && <p className="alert error" role="alert">{error}</p>}
    {!data && !error && <p role="status">در حال دریافت داشبورد…</p>}
    {data && <section className="dashboard-metrics" aria-label="آمار کلی هشتی">
      <div className="dashboard-metric dashboard-metric-primary"><span>هشتی‌نشین‌ها</span>
        <strong>{data.guest_count.toLocaleString("fa-IR")}</strong><small>نفر در بانک هشتی‌نشین‌ها</small></div>
      <div className="dashboard-metric"><span>هشتی‌های پیش‌رو</span><strong>{data.upcoming_event_count.toLocaleString("fa-IR")}</strong></div>
      <div className="dashboard-metric"><span>ثبت‌نام‌های پیش‌رو</span><strong>{data.upcoming_registration_count.toLocaleString("fa-IR")}</strong></div>
      <div className="dashboard-metric dashboard-metric-attention"><span>رسیدهای در انتظار</span><strong>{data.pending_receipt_count.toLocaleString("fa-IR")}</strong></div>
      <div className="dashboard-metric"><span>هشتی‌های برگزارشده</span><strong>{data.held_event_count.toLocaleString("fa-IR")}</strong></div>
      <div className="dashboard-metric"><span>مهمان‌های بدهکار</span><strong>{data.debtor_count.toLocaleString("fa-IR")}</strong></div>
      <div className="dashboard-metric dashboard-metric-debt"><span>مجموع بدهی</span><strong>{formatToman(data.total_debt)}</strong></div>
    </section>}
    <nav className="dashboard-shortcuts" aria-label="دسترسی سریع">
      <Link href="/panel/reports"><span>گزارش‌ها</span><small>آمار و امور مالی</small><span className="dashboard-shortcut-arrow" aria-hidden="true">←</span></Link>
      <Link href="/panel/events"><span>هشتی‌ها</span><small>برنامه‌ها و وضعیت حضور</small><span className="dashboard-shortcut-arrow" aria-hidden="true">←</span></Link>
      <Link href="/panel/guests"><span>هشتی‌نشین‌ها</span><small>پروفایل و سوابق</small><span className="dashboard-shortcut-arrow" aria-hidden="true">←</span></Link>
    </nav>
  </div></AppShell>;
}
