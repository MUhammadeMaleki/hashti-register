"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { useSession } from "@/hooks/use-session";
import { errorMessage } from "@/lib/api";
import { financeApi, type MyFinance } from "@/lib/finance";
import { formatJalali, formatToman, persianDigits } from "@/lib/format";
import { paymentsApi, type Payment } from "@/lib/payments";

export function EventGuestPayment({ eventId, cardNumber, accountHolder, onClose }: {
  eventId: number; cardNumber: string | null; accountHolder: string | null; onClose: () => void;
}) {
  const receiptInput = useRef<HTMLInputElement>(null);
  const { session, loading } = useSession();
  const [finance, setFinance] = useState<MyFinance | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [amount, setAmount] = useState("");
  const [trackingCode, setTrackingCode] = useState("");
  const [receipt, setReceipt] = useState<File | null>(null);
  const [settlementAmount, setSettlementAmount] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setFetching(true);
    try {
      const [nextFinance, nextPayments] = await Promise.all([financeApi.mine(), paymentsApi.mine()]);
      setFinance(nextFinance);
      setPayments(nextPayments.filter((payment) => payment.event_id === eventId));
      setError("");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setFetching(false); }
  }, [eventId]);

  useEffect(() => {
    if (loading || session?.actor_type !== "guest" || session.must_change_password) return;
    void refresh();
    window.addEventListener("hashti:registration", refresh);
    return () => window.removeEventListener("hashti:registration", refresh);
  }, [loading, session, refresh]);

  const registration = finance?.registrations.find((item) => item.event_id === eventId);

  async function submitReceipt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const value = Number(amount);
    if (!Number.isSafeInteger(value) || value <= 0 || (!trackingCode.trim() && !receipt)) {
      setError("مبلغ مثبت و کد پیگیری یا تصویر رسید الزامی است."); return;
    }
    if (receipt && receipt.size > 5 * 1024 * 1024) {
      setError("حجم تصویر نباید از ۵ مگابایت بیشتر باشد."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await paymentsApi.submit(value, trackingCode, receipt, eventId);
      setAmount(""); setTrackingCode(""); setReceipt(null);
      form.reset();
      await refresh();
      setNotice("رسید ثبت شد. پس از تأیید، کیف پول شارژ می‌شود؛ بدهی خودکار تسویه نمی‌شود.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function settle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(settlementAmount);
    if (!finance || !registration || !Number.isSafeInteger(value) || value <= 0 ||
      value > Math.min(registration.debt, finance.wallet_balance)) {
      setError("مبلغ تسویه باید حداکثر برابر بدهی و موجودی کیف پول باشد."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await financeApi.settleMine(registration.id, value);
      setSettlementAmount("");
      await refresh();
      window.dispatchEvent(new Event("hashti:wallet-changed"));
      setNotice("تسویهٔ این هشتی ثبت شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <section className={`event-guest-payment${registration ? "" : " is-compact"}`} id="payment">
    <div className="event-payment-dialog-top">
      <h2>پرداخت و پیگیری این هشتی</h2>
      {finance && registration && <div className="event-guest-payment-stats">
        <p>موجودی کیف پول <strong>{formatToman(finance.wallet_balance)}</strong></p>
        <p>بدهی همین هشتی <strong>{formatToman(registration.debt)}</strong></p>
        <p>تسویه‌شدهٔ همین هشتی <strong>{formatToman(registration.active_settlements)}</strong></p>
      </div>}
      <Button type="button" className="secondary event-payment-close" aria-label="بستن پنجرهٔ پرداخت"
        onClick={onClose}>×</Button>
    </div>
    {loading ? <p role="status">در حال بررسی حساب…</p> :
      session?.actor_type !== "guest" || session.must_change_password ? <>
        <p>برای واریز مبلغ ورودی لطفاً وارد هشتی شوید.</p>
        <Link className="event-guest-login" href={`/login?next=${encodeURIComponent(`/events/${eventId}`)}`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.5-4 3-6 7.5-6s7 2 7.5 6" />
          </svg>
          <span>ورود یا ثبت نام</span>
        </Link>
      </> : !finance ? <p role="status">{fetching ? "در حال دریافت اطلاعات مالی…" :
        "اطلاعات مالی در دسترس نیست؛ دوباره تلاش کنید."}</p> :
      !registration ? <><p>برای واریز مبلغ ورودی لطفاً وارد هشتی شوید.</p>
        <Link className="event-guest-login" href={`/login?next=${encodeURIComponent(`/events/${eventId}`)}`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.5-4 3-6 7.5-6s7 2 7.5 6" />
          </svg>
          <span>ورود یا ثبت نام</span>
        </Link></> : <>
        {cardNumber ? <div className="event-guest-payment-card"><span>شماره کارت هشتی</span>
          <strong dir="ltr">{persianDigits(cardNumber)}</strong>{accountHolder && <small>به نام {accountHolder}</small>}</div> :
          <p className="muted">شماره کارت هنوز در تنظیمات ثبت نشده است.</p>}
        <form className="form-stack event-receipt-form" onSubmit={submitReceipt}>
          <h3>ثبت رسید واریز برای این هشتی</h3>
          <Field id={`event-payment-amount-${eventId}`} label="مبلغ واریز (تومان)" type="number"
            min={1} value={amount} onChange={(event) => setAmount(event.target.value)} required />
          <Field id={`event-payment-code-${eventId}`} label="کد پیگیری (اختیاری)" maxLength={200}
            value={trackingCode} onChange={(event) => setTrackingCode(event.target.value)} />
          <div className="field event-receipt-file"><span>تصویر رسید (اختیاری)</span>
            <input ref={receiptInput} type="file" hidden accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
              onChange={(event) => setReceipt(event.target.files?.[0] ?? null)} />
            <div className="event-receipt-file-picker">
              <Button type="button" className="secondary" onClick={() => receiptInput.current?.click()}>
                انتخاب تصویر</Button>
              <span aria-live="polite">{receipt?.name ?? "تصویری انتخاب نشده است"}</span>
            </div>
          </div>
          <p className="muted">کد پیگیری یا تصویر لازم است؛ تصویر حداکثر ۵ مگابایت.</p>
          <Button type="submit" className="primary" disabled={busy}>ثبت رسید برای بررسی</Button>
        </form>
        {payments.length > 0 && <div className="event-guest-payment-receipts"><h3>رسیدهای همین هشتی</h3>
          {payments.map((payment) => <div key={payment.id} className="event-guest-payment-receipt">
            <strong>{formatToman(payment.amount)}</strong><span>{payment.status === "pending" ?
              "در انتظار بررسی" : payment.status === "approved" ? "تأییدشده" : "ردشده"}</span>
            <small>{formatJalali(payment.created_at)}</small>
            {payment.reject_reason && <small>دلیل رد: {payment.reject_reason}</small>}
            {payment.has_image && <a className="text-link" href={`/receipt/${payment.id}`}
              target="_blank" rel="noopener noreferrer">تصویر رسید</a>}
          </div>)}</div>}
        <div className="event-guest-payment-settlement"><h3>تسویهٔ بدهی همین هشتی</h3>
          {registration.is_cancelled ? <p>این هشتی لغو شده و تسویه مجاز نیست.</p> :
            registration.debt <= 0 ? <p>{registration.attendance === "pending" ?
              "بعد از ثبت حضور و ایجاد بدهی، امکان تسویه فعال می‌شود." : "بدهی تسویه‌نشده‌ای ندارید."}</p> :
              <form className="form-stack" onSubmit={settle}>
                <Field id={`event-settlement-${eventId}`} label="مبلغ تسویه (تومان)" type="number"
                  min={1} max={Math.min(registration.debt, finance.wallet_balance)}
                  value={settlementAmount} onChange={(event) => setSettlementAmount(event.target.value)} required />
                <Button type="submit" className="primary" disabled={busy || finance.wallet_balance <= 0}>
                  تسویه با کیف پول</Button>
                {finance.wallet_balance <= 0 && <p className="muted">موجودی کافی نیست؛ ابتدا کیف پول را شارژ کنید.</p>}
              </form>}
        </div>
      </>}
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
  </section>;
}
