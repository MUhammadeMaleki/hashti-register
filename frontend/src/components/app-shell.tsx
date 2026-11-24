"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { auth, errorMessage, type SessionInfo } from "@/lib/api";
import { useSession } from "@/hooks/use-session";
import { Button } from "@/components/ui";

export function AppShell({ kind, children }: { kind: "user" | "guest"; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { session, loading } = useSession();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);
  useEffect(() => {
    if (loading) return;
    if (!session || session.actor_type !== kind) router.replace("/login");
    else if (session.must_change_password) router.replace("/change-password");
  }, [kind, loading, router, session]);
  if (loading) return <main className="loading" role="status">در حال بررسی نشست…</main>;
  if (!session || session.actor_type !== kind || session.must_change_password) return null;
  async function logout() {
    if (busy) return;
    setBusy(true); setError("");
    try { await auth.logout(); router.replace("/login"); }
    catch (caught) { setError(errorMessage(caught)); setBusy(false); }
  }
  return <div className="app-layout">
    {menuOpen && <button type="button" className="sidebar-backdrop" aria-label="بستن منو"
      onClick={() => setMenuOpen(false)} />}
    <aside id="panel-navigation" className={`sidebar ${menuOpen ? "is-open" : ""}`}>
      <button type="button" className="sidebar-close" aria-label="بستن منو"
        onClick={() => setMenuOpen(false)}>×</button>
      <Link href="/" className="brand"><span className="public-brand-mark"><img src="/hashti-mark.svg" alt="" /></span>
        <span>هشتی<span className="brand-dot">.</span></span></Link>
      <p className="sidebar-label">{kind === "user" ? "پنل مدیریت" : "حساب هشتی‌نشینی"}</p>
      <nav aria-label="ناوبری اصلی" onClick={() => setMenuOpen(false)}>
        <Link className={`nav-link ${pathname === (kind === "user" ? "/panel" : "/account") ? "active" : ""}`}
          href={kind === "user" ? "/panel" : "/account"}>
          نمای کلی
        </Link>
        {kind === "user" ?
          <Link className={`nav-link ${pathname.startsWith("/panel/events") ? "active" : ""}`}
            href="/panel/events">هشتی‌ها</Link> :
          <Link className="nav-link" href="/account#registrations">هشتی‌های من</Link>}
        {kind === "user" && <Link className={`nav-link ${pathname === "/panel/locations" ? "active" : ""}`}
          href="/panel/locations">کافه‌ها</Link>}
        {kind === "user" ?
          <Link className={`nav-link ${pathname.startsWith("/panel/guests") ? "active" : ""}`}
            href="/panel/guests">هشتی‌نشین‌ها</Link> :
          <Link className="nav-link" href="/account#wallet">کیف پول</Link>}
        {kind === "user" ?
          <Link className={`nav-link ${pathname.startsWith("/panel/payments") ? "active" : ""}`}
            href="/panel/payments">بررسی رسیدها</Link> :
          <Link className="nav-link" href="/account#receipts">پرداخت‌ها</Link>}
        {kind === "user" && <Link className={`nav-link ${pathname === "/panel/reports" ? "active" : ""}`}
          href="/panel/reports">گزارش‌ها</Link>}
        {kind === "user" &&
          <Link className={`nav-link ${pathname === "/panel/settings" || pathname === "/panel/users" ? "active" : ""}`}
            href="/panel/settings">حساب‌ها و تنظیمات</Link>}
      </nav>
    </aside>
    <div className="workspace"><header className={`workspace-header ${kind === "user" ? "admin-header" : "guest-header"}`}>
      <button type="button" className="workspace-menu-toggle" aria-label="باز کردن منو"
        aria-expanded={menuOpen} aria-controls="panel-navigation" onClick={() => setMenuOpen(true)}>
        <span /><span /><span /></button>
      {kind === "guest" ? <Link href="/" className="guest-header-brand">
        <span className="guest-header-mark"><img src="/hashti-mark.svg" alt="" /></span>
        <span><small>هشتی</small><strong>حساب من</strong></span>
      </Link> : <div className="workspace-title"><span className="eyebrow">هشتی / فضای مدیریت</span>
        <h1>{pathname === "/panel/users" || pathname === "/panel/settings" ? "حساب‌ها و تنظیمات" :
          pathname.startsWith("/panel/events") ? "هشتی‌ها" :
          pathname.startsWith("/panel/guests") || pathname === "/panel/import" ? "هشتی‌نشین‌ها" :
          pathname.startsWith("/panel/payments") ? "بررسی رسیدها" :
          pathname === "/panel/reports" ? "گزارش‌ها" :
          pathname === "/panel/locations" ? "کافه‌ها" :
          "نمای کلی"}</h1></div>}
      <div className="workspace-session">{kind === "user" ?
        <div className="admin-session-identity"><span className="admin-session-mark" aria-hidden="true">
          <img src="/hashti-mark.svg" alt="" /></span>
          <span><small>حساب فعال</small><strong>{roleName(session)}</strong></span></div> :
        <Link className="guest-header-home" href="/">دیدن هشتی‌ها <span aria-hidden="true">↗</span></Link>}
        <Button type="button" onClick={logout} disabled={busy} className="secondary workspace-logout">خروج</Button>
        {error && <p className="alert error" role="alert">{error}</p>}
      </div>
    </header><main className="workspace-main">{children}</main></div>
  </div>;
}

function roleName(session: SessionInfo): string {
  if (session.actor_type === "guest") return "هشتی‌نشین";
  return session.role === "super_admin" ? "مدیر هشتی" : "دبیر";
}
