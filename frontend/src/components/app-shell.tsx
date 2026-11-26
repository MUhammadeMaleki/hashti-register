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
  const [accountSection, setAccountSection] = useState("");
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    const syncSection = () => setAccountSection(window.location.hash);
    syncSection();
    window.addEventListener("hashchange", syncSection);
    return () => window.removeEventListener("hashchange", syncSection);
  }, [pathname]);
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
      <p className="sidebar-label">{kind === "user" ? "پنل مدیریت" : "حساب هشتی‌نشینی"}</p>
      <nav aria-label="ناوبری اصلی" onClick={() => setMenuOpen(false)}>
        <Link className={`nav-link ${pathname === (kind === "user" ? "/panel" : "/account") && (kind === "user" || !accountSection) ? "active" : ""}`}
          href={kind === "user" ? "/panel" : "/account"}>
          <NavIcon name="home" />نمای کلی
        </Link>
        {kind === "user" ?
          <Link className={`nav-link ${pathname.startsWith("/panel/events") ? "active" : ""}`}
            href="/panel/events"><NavIcon name="events" />هشتی‌ها (رویدادها)</Link> :
          <Link className={`nav-link ${accountSection === "#registrations" ? "active" : ""}`} href="/account#registrations"><NavIcon name="events" />هشتی‌های من</Link>}
        {kind === "user" && <Link className={`nav-link ${pathname === "/panel/locations" ? "active" : ""}`}
          href="/panel/locations"><NavIcon name="location" />کافه‌ها</Link>}
        {kind === "user" ?
          <Link className={`nav-link ${pathname.startsWith("/panel/guests") ? "active" : ""}`}
            href="/panel/guests"><NavIcon name="people" />هشتی‌نشین‌ها</Link> :
          <Link className={`nav-link ${accountSection === "#wallet" ? "active" : ""}`} href="/account#wallet"><NavIcon name="wallet" />کیف پول</Link>}
        {kind === "user" ?
          <Link className={`nav-link ${pathname.startsWith("/panel/payments") ? "active" : ""}`}
            href="/panel/payments"><NavIcon name="receipt" />بررسی رسیدها</Link> :
          <Link className={`nav-link ${accountSection === "#receipts" ? "active" : ""}`} href="/account#receipts"><NavIcon name="receipt" />پرداخت‌ها</Link>}
        {kind === "user" && <Link className={`nav-link ${pathname === "/panel/reports" ? "active" : ""}`}
          href="/panel/reports"><NavIcon name="reports" />گزارش‌ها</Link>}
        {kind === "user" &&
          <Link className={`nav-link ${pathname === "/panel/settings" || pathname === "/panel/users" ? "active" : ""}`}
            href="/panel/settings"><NavIcon name="settings" />حساب‌ها و تنظیمات</Link>}
      </nav>
    </aside>
    <div className="workspace"><header className={`workspace-header ${kind === "user" ? "admin-header" : "guest-header"}`}>
      <button type="button" className="workspace-menu-toggle" aria-label="باز کردن منو"
        aria-expanded={menuOpen} aria-controls="panel-navigation" onClick={() => setMenuOpen(true)}>
        <span /><span /><span /></button>
      {kind === "guest" ? <Link href="/" className="guest-header-brand">
        <span className="guest-header-mark"><img src="/hashti-mark.svg" alt="" /></span>
        <span><small>هشتی</small><strong>حساب من</strong></span>
      </Link> : <div className="admin-title-group">
        <Link href="/" className="admin-home-mark" aria-label="بازگشت به صفحهٔ اصلی" title="صفحهٔ اصلی">
          <img src="/hashti-mark.svg" alt="" />
        </Link>
        <div className="workspace-title"><span className="eyebrow">هشتی / فضای مدیریت</span>
        <h1>{pathname === "/panel/users" || pathname === "/panel/settings" ? "حساب‌ها و تنظیمات" :
          pathname.startsWith("/panel/events") ? "هشتی‌ها" :
          pathname.startsWith("/panel/guests") || pathname === "/panel/import" ? "هشتی‌نشین‌ها" :
          pathname.startsWith("/panel/payments") ? "بررسی رسیدها" :
          pathname === "/panel/reports" ? "گزارش‌ها" :
          pathname === "/panel/locations" ? "کافه‌ها" :
          "نمای کلی"}</h1></div></div>}
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

function NavIcon({ name }: { name: "home" | "events" | "location" | "people" | "wallet" | "receipt" | "reports" | "settings" }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "home" && <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z" /><path d="M9 21v-7h6v7" /></>}
    {name === "events" && <><rect x="4" y="5" width="16" height="16" rx="3" /><path d="M7 5V3m10 2V3M4 11h16M8 15h3m-3 3h3" /></>}
    {name === "location" && <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2.5" /></>}
    {name === "people" && <><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2H3Z" /><circle cx="17" cy="8" r="2.5" /><path d="M17 14a5 5 0 0 1 4 5v1h-3" /></>}
    {name === "wallet" && <><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M3 9V5a2 2 0 0 1 2-2h13m3 9h-6a2 2 0 0 0 0 4h6" /></>}
    {name === "receipt" && <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6m-6 4h6m-6 4h3" /></>}
    {name === "reports" && <><path d="M3 21h18" /><rect x="5" y="12" width="3" height="7" rx="1" /><rect x="11" y="8" width="3" height="11" rx="1" /><rect x="17" y="4" width="3" height="15" rx="1" /></>}
    {name === "settings" && <><circle cx="12" cy="12" r="3" /><path d="M10 3h4l.5 2.2 1.6.9 2.2-.7 2 3.4-1.7 1.6v1.8l1.7 1.6-2 3.4-2.2-.7-1.6.9L14 21h-4l-.5-2.2-1.6-.9-2.2.7-2-3.4 1.7-1.6v-1.8l-1.7-1.6 2-3.4 2.2.7 1.6-.9L10 3Z" /></>}
  </svg>;
}
