"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "@/hooks/use-session";
import { financeApi } from "@/lib/finance";
import { formatToman } from "@/lib/format";

export function PublicHeader({ backHref, backLabel, hideAccountActions = false }: {
  backHref?: string; backLabel?: string; hideAccountActions?: boolean;
}) {
  const { session, loading } = useSession();
  const [walletBalance, setWalletBalance] = useState<number | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);

  useEffect(() => {
    if (loading || session?.actor_type !== "guest") return;
    let active = true;
    const refresh = () => {
      financeApi.mine().then((finance) => {
        if (active) setWalletBalance(finance.wallet_balance);
      }).catch(() => {
        if (active) setWalletBalance(null);
      }).finally(() => {
        if (active) setWalletLoading(false);
      });
    };
    refresh();
    window.addEventListener("hashti:wallet-changed", refresh);
    return () => { active = false; window.removeEventListener("hashti:wallet-changed", refresh); };
  }, [loading, session?.actor_type, session?.actor_id]);

  const balanceLabel = walletLoading ? "در حال دریافت موجودی…" :
    walletBalance === null ? "موجودی نامشخص" : formatToman(walletBalance);
  return <header className="public-header">
    <Link className="brand public-brand" href="/">
      <span className="public-brand-mark"><img src="/hashti-mark.svg" alt="" /></span>
      <span>هشتی<span className="brand-dot">.</span></span>
    </Link>
    <nav className="public-header-actions" aria-label="پیوندهای حساب و صفحه">
      {backHref && backLabel && <Link className="button secondary" href={backHref}>{backLabel}</Link>}
      {!hideAccountActions && !loading && (session?.actor_type === "guest" ? <>
        <Link className="public-icon-link" href="/account#profile" aria-label="پروفایل من"
          title="پروفایل من"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.5-4 3-6 7.5-6s7 2 7.5 6" />
          </svg></Link>
        <Link className="public-icon-link public-wallet-link" href="/account#wallet"
          aria-label={`کیف پول من؛ ${balanceLabel}`} title="کیف پول من">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="6" width="18" height="14" rx="2" />
            <path d="M3 9V5a2 2 0 0 1 2-2h13" />
            <path d="M16 13h5v4h-5a2 2 0 0 1 0-4Z" />
          </svg><span>{balanceLabel}</span></Link>
      </> : session?.actor_type === "user" ?
        <Link className="button secondary" href="/panel">پنل مدیریت</Link> :
        <Link className="button secondary" href="/login">ورود به سامانه</Link>)}
    </nav>
  </header>;
}
