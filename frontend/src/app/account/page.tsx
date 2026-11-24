"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { Button, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { financeApi, type GuestProfile, type MyFinance, type WalletTransaction } from "@/lib/finance";
import { formatJalali, formatToman, latinDigits, persianDigits } from "@/lib/format";
import { paymentsApi, type Payment } from "@/lib/payments";

const transactionNames: Record<string, string> = {
  topup: "شارژ کیف پول", settlement: "تسویهٔ رویداد",
  refund: "بازگشت اعتبار", manual_adjust: "اصلاح دستی موجودی",
};

type Registration = MyFinance["registrations"][number];
type RegistrationFilter = "all" | "debt" | "present" | "pending";
const registrationsPerPage = 6;

function registrationTime(row: Registration): string {
  if (row.time_mode === "exact" && row.event_date && row.start_time)
    return `${formatJalali(`${row.event_date}T12:00:00Z`)}، ساعت ${persianDigits(row.start_time.slice(0, 5))}`;
  if (row.time_mode === "approximate") return persianDigits(row.time_text || "زمان تقریبی");
  return "زمان به‌زودی اعلام می‌شود";
}

function registrationPlace(row: Registration): string {
  if (row.location_mode === "exact") return row.location_title || "مکان به‌زودی اعلام می‌شود";
  if (row.location_mode === "approximate") return persianDigits(row.location_text || "مکان تقریبی");
  return "مکان به‌زودی اعلام می‌شود";
}

export default function AccountPage() {
  const [data, setData] = useState<MyFinance | null>(null);
  const [profile, setProfile] = useState<GuestProfile | null>(null);
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [registrationFilter, setRegistrationFilter] = useState<RegistrationFilter>("all");
  const [registrationSearch, setRegistrationSearch] = useState("");
  const [registrationPage, setRegistrationPage] = useState(1);
  const [expandedSettlement, setExpandedSettlement] = useState<number | null>(null);
  const settlementDialogRef = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [payments, setPayments] = useState<Payment[]>([]);
  const [receiptAmount, setReceiptAmount] = useState("");
  const [trackingCode, setTrackingCode] = useState("");
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [receiptEvent, setReceiptEvent] = useState("");
  const [receiptPickerOpen, setReceiptPickerOpen] = useState(false);
  const receiptPickerRef = useRef<HTMLDivElement>(null);
  const receiptPickerButtonRef = useRef<HTMLButtonElement>(null);
  const [submittingReceipt, setSubmittingReceipt] = useState(false);
  useEffect(() => {
    if (!receiptPickerOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!receiptPickerRef.current?.contains(event.target as Node)) setReceiptPickerOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setReceiptPickerOpen(false);
        receiptPickerButtonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [receiptPickerOpen]);
  useEffect(() => {
    let active = true;
    Promise.all([financeApi.mine(), financeApi.profile(), financeApi.transactions(),
      paymentsApi.mine()]).then(([finance, guest, ledger, receipts]) => {
      if (active) { setData(finance); setProfile(guest); setTransactions(ledger); setPayments(receipts); }
    })
      .catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, []);

  async function settle(event: FormEvent<HTMLFormElement>, id: number, debt: number) {
    event.preventDefault();
    const amount = Number(latinDigits(amounts[id] ?? ""));
    if (!data || !Number.isSafeInteger(amount) || amount <= 0 ||
        amount > Math.min(debt, data.wallet_balance)) {
      setError("مبلغ باید مثبت و حداکثر برابر بدهی و موجودی کیف پول باشد."); return;
    }
    setBusyId(id); setError(""); setNotice("");
    try {
      await financeApi.settleMine(id, amount);
      const [finance, ledger] = await Promise.all([financeApi.mine(), financeApi.transactions()]);
      setData(finance); setTransactions(ledger);
      setAmounts((previous) => ({ ...previous, [id]: "" }));
      setExpandedSettlement(null);
      setNotice("تسویه ثبت شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusyId(null); }
  }

  async function submitReceipt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(latinDigits(receiptAmount));
    if (!Number.isSafeInteger(amount) || amount <= 0 || (!trackingCode.trim() && !receiptFile)) {
      setError("مبلغ مثبت و کد پیگیری یا تصویر رسید الزامی است."); return;
    }
    if (receiptFile && receiptFile.size > 5 * 1024 * 1024) {
      setError("حجم تصویر نباید از ۵ مگابایت بیشتر باشد."); return;
    }
    setSubmittingReceipt(true); setError(""); setNotice("");
    try {
      await paymentsApi.submit(amount, latinDigits(trackingCode), receiptFile,
        receiptEvent ? Number(receiptEvent) : null);
      setPayments(await paymentsApi.mine());
      setReceiptAmount(""); setTrackingCode(""); setReceiptFile(null);
      const input = document.getElementById("receipt-image") as HTMLInputElement | null;
      if (input) input.value = "";
      setNotice("رسید برای بررسی ثبت شد؛ موجودی کیف پول پس از تأیید تغییر می‌کند.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setSubmittingReceipt(false); }
  }

  const totalDebt = data?.registrations.reduce((sum, row) => sum + row.debt, 0) ?? 0;
  const pendingReceipts = payments.filter((item) => item.status === "pending").length;
  const matchingRegistrations = data?.registrations.filter((row) => {
    const query = latinDigits(registrationSearch).trim().toLocaleLowerCase("fa-IR");
    const matchesSearch = !query || `${row.title} ${row.event_number} ${registrationPlace(row)}`
      .toLocaleLowerCase("fa-IR").includes(query);
    const matchesFilter = registrationFilter === "all" ||
      (registrationFilter === "debt" && row.debt > 0) ||
      (registrationFilter === "present" && row.attendance === "present") ||
      (registrationFilter === "pending" && row.attendance === "pending");
    return matchesSearch && matchesFilter;
  }) ?? [];
  const registrationPages = Math.max(1, Math.ceil(matchingRegistrations.length / registrationsPerPage));
  const currentRegistrationPage = Math.min(registrationPage, registrationPages);
  const visibleRegistrations = matchingRegistrations.slice(
    (currentRegistrationPage - 1) * registrationsPerPage, currentRegistrationPage * registrationsPerPage);
  const settlementRegistration = data?.registrations.find((row) => row.id === expandedSettlement) ?? null;

  useEffect(() => {
    const dialog = settlementDialogRef.current;
    if (settlementRegistration && dialog && !dialog.open) dialog.showModal();
  }, [settlementRegistration]);

  return <AppShell kind="guest"><div className="guest-account">
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    {!data && !error && <p role="status" className="guest-account-loading">در حال دریافت اطلاعات حساب…</p>}
    {data && <>
      <div className="guest-account-top">
        <section id="profile" className="guest-profile-hero">
          <div className="guest-profile-main">
            <div className="guest-profile-brand"><img src="/hashti-mark.svg" alt="" /> <span>پروفایل هشتی‌نشین</span></div>
            <div className="guest-profile-copy"><span>اینجا جای تو در هشتی است</span>
              <h2>{profile ? `${profile.first_name} ${profile.last_name}` : "هشتی‌نشین عزیز"}<em>، خوش آمدی.</em></h2>
              <p>هشتی‌هایی که در آن‌ها نشسته‌ای و وضعیت حساب خودت را اینجا دنبال کن.</p>
            </div>
            {profile && <div className="guest-profile-tags">
              <span>شمارهٔ همراه: <bdi>{persianDigits(profile.phone)}</bdi></span>
              {profile.age !== null && <span>سن: {persianDigits(String(profile.age))}</span>}
              {profile.gender && <span>جنسیت: {profile.gender}</span>}
              {profile.education && <span>تحصیلات: {profile.education}</span>}
            </div>}
          </div>
          <section id="wallet" className="guest-wallet-hero">
            <span>کیف پول هشتی‌نشینی</span><h2>اعتبار قابل استفاده</h2>
            <strong>{formatToman(data.wallet_balance)}</strong>
            <p>اعتبار فقط با انتخاب شما برای بدهی هشتی‌ها مصرف می‌شود.</p>
            <a href="#receipts">ثبت واریز جدید <span aria-hidden="true">←</span></a>
          </section>
          <nav className="guest-profile-shortcuts" aria-label="دسترسی سریع پروفایل">
            <a href="#registrations">هشتی‌های من <span aria-hidden="true">↙</span></a>
            <a href="#receipts">رسیدهای من <span aria-hidden="true">↙</span></a>
            <a href="#transactions">گردش کیف پول <span aria-hidden="true">↙</span></a>
          </nav>
        </section>
      </div>
      <div className="guest-account-stats" aria-label="خلاصهٔ حساب">
        <div><span>هشتی‌های من</span><strong>{persianDigits(String(data.registrations.length))}</strong></div>
        <div><span>بدهی هشتی‌ها</span><strong>{formatToman(totalDebt)}</strong></div>
        <div><span>رسید در انتظار بررسی</span><strong>{persianDigits(String(pendingReceipts))}</strong></div>
      </div>
      <div className="guest-account-main">
        <section id="registrations" className="guest-account-panel guest-registrations">
          <div className="guest-panel-heading"><div><span>هشتی‌نشینی‌های من</span><h2>ثبت‌نام‌ها</h2></div>
            <strong>{persianDigits(String(data.registrations.length))} هشتی</strong></div>
          <div className="guest-registration-toolbar">
            <div className="guest-registration-filters" role="group" aria-label="فیلتر هشتی‌ها">
              {([ ["all", "همه"], ["debt", "دارای بدهی"], ["present", "حاضر"], ["pending", "در انتظار حضور"] ] as const)
                .map(([key, label]) => <button key={key} type="button"
                  className={registrationFilter === key ? "is-active" : ""}
                  aria-pressed={registrationFilter === key}
                  onClick={() => { setRegistrationFilter(key); setRegistrationPage(1); }}>{label}</button>)}
            </div>
            <label className="guest-registration-search"><span className="sr-only">جست‌وجوی هشتی‌ها</span>
              <input type="search" placeholder="جست‌وجوی نام، شماره یا مکان…" value={registrationSearch}
                onChange={(event) => { setRegistrationSearch(event.target.value); setRegistrationPage(1); }} /></label>
          </div>
          <div className="guest-registration-list">{visibleRegistrations.map((row) =>
            <article className="guest-registration" key={row.id}>
              <div className="guest-registration-top">
                <Link className={`guest-registration-poster${row.poster_url ? "" : " is-empty"}`}
                  href={`/events/${row.event_id}`} aria-label={`دیدن ${row.title}`}>
                  <img src={row.poster_url || "/hashti-mark.svg"} alt="" loading="lazy" /></Link>
                <div className="guest-registration-summary">
                <div className="guest-registration-head"><div><span>هشتی شمارهٔ {persianDigits(String(row.event_number))}</span>
                  <h3><Link href={`/events/${row.event_id}`}>{persianDigits(row.title)}</Link></h3></div>
                  <span className={`guest-registration-status ${row.is_cancelled ? "is-cancelled" :
                    row.attendance === "present" ? "is-present" : row.attendance === "pending" ? "is-pending" : "is-absent"}`}>
                    {row.is_cancelled ? "لغوشده" : row.attendance === "present" ? "حاضر" :
                      row.attendance === "pending" ? "حضور نامشخص" : "غایب"}</span></div>
                  <div className="guest-registration-facts">
                    <div><span>هزینه</span><strong>{formatToman(row.active_charges)}</strong></div>
                    <div><span>تسویه‌شده</span><strong>{formatToman(row.active_settlements)}</strong></div>
                    <div className={row.debt > 0 ? "has-debt" : ""}><span>مانده بدهی</span><strong>{formatToman(row.debt)}</strong></div>
                  </div>
                </div>
              </div>
              <div className="guest-registration-meta"><span>زمان: {registrationTime(row)}</span>
                <span>مکان: {registrationPlace(row)}</span>
                <span>ورودی: {row.entry_fee === 0 ? "رایگان" : formatToman(row.entry_fee)}</span></div>
              <div className="guest-registration-actions">
                {row.is_cancelled ? <p className="guest-registration-note">این هشتی لغو شده و تسویهٔ آن فعلاً مجاز نیست.</p> :
                row.debt > 0 && <button type="button"
                  className="guest-settlement-toggle" aria-haspopup="dialog"
                  onClick={() => setExpandedSettlement(row.id)}>
                  تسویهٔ این هشتی <span aria-hidden="true">←</span></button>}
              </div>
            </article>)}
            {!data.registrations.length && <div className="guest-account-empty">هنوز در هشتی‌ای ثبت‌نام نکرده‌اید.
              <Link href="/">دیدن هشتی‌های باز ←</Link></div>}
            {!!data.registrations.length && !matchingRegistrations.length &&
              <div className="guest-account-empty">هشتی‌ای با این جست‌وجو یا فیلتر پیدا نشد.</div>}
          </div>
          {settlementRegistration && !settlementRegistration.is_cancelled && settlementRegistration.debt > 0 &&
            <dialog ref={settlementDialogRef} className="guest-settlement-dialog"
              aria-labelledby="guest-settlement-title" onClose={() => setExpandedSettlement(null)}
              onClick={(event) => { if (event.target === event.currentTarget) setExpandedSettlement(null); }}>
              <div className="guest-settlement-dialog-head"><div><span>تسویه با کیف پول</span>
                <h3 id="guest-settlement-title">{persianDigits(settlementRegistration.title)}</h3></div>
                <button type="button" aria-label="بستن" onClick={() => setExpandedSettlement(null)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 5 19 19M19 5 5 19" fill="none" stroke="currentColor" strokeWidth="2"
                      strokeLinecap="round" />
                  </svg>
                </button></div>
              <p>مانده بدهی: <strong>{formatToman(settlementRegistration.debt)}</strong> · موجودی کیف پول: <strong>{formatToman(data.wallet_balance)}</strong></p>
              <form className="guest-settlement-form" onSubmit={(event) => settle(event, settlementRegistration.id, settlementRegistration.debt)}>
                <Field id={`settle-${settlementRegistration.id}`} label="مبلغ تسویه (تومان)" inputMode="numeric" pattern="[۰-۹0-9]*"
                  value={amounts[settlementRegistration.id] ?? ""} onChange={(event) => setAmounts((previous) =>
                    ({ ...previous, [settlementRegistration.id]: persianDigits(latinDigits(event.target.value).replace(/[^0-9]/g, "")) }))} required />
                <Button type="submit" className="secondary" disabled={busyId !== null || data.wallet_balance <= 0}>
                  تسویه با کیف پول</Button>
                {data.wallet_balance <= 0 && <small>برای تسویه، ابتدا <a href="#receipts" onClick={() => setExpandedSettlement(null)}>کیف پول را شارژ کنید.</a></small>}
              </form>
            </dialog>}
          {registrationPages > 1 && <nav className="guest-registration-pagination" aria-label="صفحه‌های هشتی‌ها">
            <button type="button" disabled={currentRegistrationPage === 1}
              onClick={() => setRegistrationPage(currentRegistrationPage - 1)}>صفحهٔ قبل</button>
            <span>صفحهٔ {persianDigits(String(currentRegistrationPage))} از {persianDigits(String(registrationPages))}</span>
            <button type="button" disabled={currentRegistrationPage === registrationPages}
              onClick={() => setRegistrationPage(currentRegistrationPage + 1)}>صفحهٔ بعد</button>
          </nav>}
        </section>
      </div>
      <section id="receipts" className="guest-account-panel guest-receipt-panel">
            <div className="guest-panel-heading"><div><span>شارژ کیف پول</span><h2>ثبت رسید واریز</h2></div></div>
            <p className="guest-panel-description">پس از بررسی و تأیید رسید، مبلغ به کیف پول شما اضافه می‌شود.</p>
            <form className="guest-receipt-form" onSubmit={submitReceipt}>
              <Field id="receipt-amount" label="مبلغ پرداخت (تومان)" inputMode="numeric" pattern="[۰-۹0-9]*"
                value={receiptAmount} onChange={(event) => setReceiptAmount(persianDigits(latinDigits(event.target.value)
                  .replace(/[^0-9]/g, "")))} required />
              <div className="field guest-receipt-picker" ref={receiptPickerRef}>
                <label htmlFor="receipt-event">برای کدام هشتی؟</label>
                <button id="receipt-event" ref={receiptPickerButtonRef} type="button"
                  className="guest-receipt-picker-trigger" aria-expanded={receiptPickerOpen}
                  aria-controls="receipt-event-options" onClick={() => setReceiptPickerOpen(!receiptPickerOpen)}>
                  <span>{receiptEvent ? (() => {
                    const row = data.registrations.find((item) => String(item.event_id) === receiptEvent);
                    return row ? `هشتی ${persianDigits(String(row.event_number))} · ${persianDigits(row.title)}` : "شارژ مستقل کیف پول";
                  })() : "شارژ مستقل کیف پول"}</span>
                  <span className="guest-receipt-picker-chevron" aria-hidden="true" />
                </button>
                {receiptPickerOpen && <div id="receipt-event-options" className="guest-receipt-picker-options">
                  <button type="button" aria-pressed={receiptEvent === ""} onClick={() => {
                    setReceiptEvent(""); setReceiptPickerOpen(false); receiptPickerButtonRef.current?.focus();
                  }}>شارژ مستقل کیف پول</button>
                  {data.registrations.filter((row) => !row.is_cancelled).map((row) =>
                    <button key={row.event_id} type="button" aria-pressed={receiptEvent === String(row.event_id)}
                      onClick={() => {
                        setReceiptEvent(String(row.event_id)); setReceiptPickerOpen(false);
                        receiptPickerButtonRef.current?.focus();
                      }}>هشتی {persianDigits(String(row.event_number))} · {persianDigits(row.title)}</button>)}
                </div>}
              </div>
              <Field id="receipt-code" label="کد پیگیری (اختیاری)" maxLength={200}
                value={trackingCode} onChange={(event) => setTrackingCode(persianDigits(latinDigits(event.target.value)))} />
              <div className="guest-file-field"><span>تصویر رسید (اختیاری)</span>
                <input id="receipt-image" className="sr-only" type="file"
                  accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
                  onChange={(event) => setReceiptFile(event.target.files?.[0] ?? null)} />
                <label htmlFor="receipt-image">{receiptFile ? receiptFile.name : "انتخاب تصویر رسید"}</label></div>
              <small>کد پیگیری یا تصویر، دست‌کم یکی لازم است. تصویر حداکثر ۵ مگابایت.</small>
              <Button type="submit" disabled={submittingReceipt}>{submittingReceipt ? "در حال ثبت…" : "ثبت برای بررسی"}</Button>
            </form>
      </section>
      <div className="guest-account-side">
          <section id="transactions" className="guest-account-panel guest-transactions">
            <div className="guest-panel-heading"><div><span>رد پای اعتبار</span><h2>گردش کیف پول</h2></div></div>
            <div className="guest-transaction-list">{transactions.map((item) =>
              <div className="guest-transaction" key={item.id}>
                <span className={item.amount < 0 ? "is-out" : "is-in"} aria-hidden="true">{item.amount < 0 ? "↗" : "↙"}</span>
                <div><strong>{transactionNames[item.type] ?? item.type}</strong>
                  <small>{formatJalali(item.created_at)}{item.note && ` · ${persianDigits(item.note)}`}</small></div>
                <b>{formatToman(item.amount)}</b>
              </div>)}
              {!transactions.length && <p className="guest-account-empty">تراکنشی ثبت نشده است.</p>}
            </div>
          </section>
        <section className="guest-account-panel guest-payment-history">
        <div className="guest-panel-heading"><div><span>پیگیری پرداخت‌ها</span><h2>رسیدهای من</h2></div>
          <strong>{persianDigits(String(payments.length))} رسید</strong></div>
        <div className="guest-payment-list">{payments.map((item) =>
          <article className="guest-payment" key={item.id}>
            <div><span>رسید شمارهٔ {persianDigits(String(item.id))}</span><strong>{formatToman(item.amount)}</strong>
              <small>{formatJalali(item.created_at)} · {item.event_id === null ? "شارژ مستقل" :
                `هشتی ${persianDigits(String(data.registrations.find((row) => row.event_id === item.event_id)?.event_number ?? item.event_id))}`}</small></div>
            <span className={`guest-payment-status is-${item.status}`}>
              {item.status === "pending" ? "در انتظار بررسی" : item.status === "approved" ? "تأییدشده" : "ردشده"}</span>
            {item.tracking_code && <p>کد پیگیری: {persianDigits(item.tracking_code)}</p>}
            {item.reject_reason && <p>دلیل رد: {item.reject_reason}</p>}
            {item.has_image && <a href={`/receipt/${item.id}`} target="_blank"
              rel="noopener noreferrer">دیدن تصویر رسید ←</a>}
          </article>)}
          {!payments.length && <p className="guest-account-empty">هنوز رسیدی ثبت نشده است.</p>}
        </div>
        </section>
      </div>
    </>}
  </div></AppShell>;
}
