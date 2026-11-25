"use client";

import { useState, type FormEvent } from "react";
import { Button, Card, Field, MoneyField } from "@/components/ui";
import { SettlementOperations } from "@/components/guests/settlement-operations";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { guestsApi, type GuestProfile } from "@/lib/guests";
import styles from "./guest-profile.module.css";

export function GuestFinance({ profile, onChanged }: {
  profile: GuestProfile; onChanged: () => Promise<void>;
}) {
  const [direction, setDirection] = useState<"increase" | "decrease">("increase");
  const [adjustAmount, setAdjustAmount] = useState("");
  const [note, setNote] = useState("");
  const [registrationId, setRegistrationId] = useState<number | null>(null);
  const [settleAmount, setSettleAmount] = useState("");
  const [discountAmount, setDiscountAmount] = useState("");
  const [discountReason, setDiscountReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const active = profile.registrations.filter((row) => row.status === "active");
  const chosen = active.find((row) => row.id === registrationId);
  const walletValue = Number(settleAmount);
  const discountValue = Number(discountAmount);
  const canSettle = !!chosen && !chosen.event.is_cancelled &&
    Number.isSafeInteger(walletValue) && Number.isSafeInteger(discountValue) &&
    walletValue >= 0 && discountValue >= 0 && walletValue + discountValue > 0 &&
    walletValue <= (profile.wallet_balance ?? 0) &&
    walletValue + discountValue <= chosen.outstanding_total &&
    (discountValue === 0 || !!discountReason.trim());

  async function run(action: () => Promise<unknown>, success: string): Promise<boolean> {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await onChanged(); setRevision((value) => value + 1);
      setNotice(success); return true; }
    catch (caught) { setError(errorMessage(caught)); return false; }
    finally { setBusy(false); }
  }

  async function adjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(adjustAmount);
    if (!Number.isSafeInteger(value) || value <= 0 || !note.trim()) {
      setError("مبلغ مثبت و توضیح الزامی است."); return;
    }
    if (await run(() => guestsApi.adjustWallet(profile.id,
      direction === "increase" ? value : -value, note.trim()),
    "اصلاح کیف پول ثبت شد؛ بدهی هشتی‌ها خودکار تسویه نشد.")) {
      setAdjustAmount(""); setNote("");
    }
  }

  async function settle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!chosen) return;
    const value = Number(settleAmount);
    const discount = Number(discountAmount);
    if (!Number.isSafeInteger(value) || !Number.isSafeInteger(discount) ||
        value < 0 || discount < 0 || value + discount <= 0 ||
        value + discount > chosen.outstanding_total ||
        value > (profile.wallet_balance ?? 0) ||
        (discount > 0 && !discountReason.trim())) {
      setError("مجموع برداشت و تخفیف نباید از بدهی بیشتر شود؛ تخفیف دلیل می‌خواهد."); return;
    }
    if (await run(() => guestsApi.settle(chosen.id, value, discount,
      discountReason.trim()), "تسویه و تخفیف هشتی ثبت شد.")) {
      setSettleAmount(""); setDiscountAmount(""); setDiscountReason("");
    }
  }

  return <Card title="عملیات مالی">
    <div className={styles.financeOverview}><p>بدهی هشتی‌ها: {formatToman(profile.finance_overview.total_debt)} · بدهی خالص پس از اعتبار:
      {" "}{formatToman(profile.finance_overview.net_debt)}</p>
    <p>سقف بدهی: {profile.finance_overview.debt_ceiling === null ? "تعیین‌نشده" :
      formatToman(profile.finance_overview.debt_ceiling)}</p></div>
    {profile.finance_overview.over_ceiling && <p className="alert error" role="status">
      هشدار: بدهی خالص از سقف تعیین‌شده بیشتر است؛ ثبت هزینه مسدود نمی‌شود.</p>}
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    <div className={styles.financeGrid}><section className={styles.financeAction}>
    <h3>اصلاح دستی کیف پول</h3>
    <form className="form-stack" onSubmit={adjust}>
      <div className="field-row"><div className="field"><label htmlFor="adjust-direction">نوع</label>
        <select id="adjust-direction" value={direction} onChange={(event) =>
          setDirection(event.target.value as "increase" | "decrease")}>
          <option value="increase">افزایش</option><option value="decrease">کاهش</option>
        </select></div><MoneyField id="adjust-amount" label="مبلغ (تومان)"
        value={adjustAmount} onValueChange={setAdjustAmount} required /></div>
      <Field id="adjust-note" label="توضیح اجباری" value={note}
        onChange={(event) => setNote(event.target.value)} required />
      <Button type="submit" className="secondary" disabled={busy}>ثبت اصلاح</Button>
    </form>
    </section><section className={styles.financeAction}>
    <h3>تسویهٔ هشتی</h3>
    <div className="field"><label htmlFor="finance-registration">ثبت‌نام</label>
      <select id="finance-registration" value={registrationId ?? ""} onChange={(event) => {
        setRegistrationId(event.target.value ? Number(event.target.value) : null);
      }}><option value="">انتخاب هشتی</option>{active.map((row) =>
        <option key={row.id} value={row.id}>هشتی {row.event.event_number.toLocaleString("fa-IR")} · {row.event.title}</option>)}</select>
    </div>
    {chosen && <><p>بدهی: {formatToman(chosen.outstanding_total)} · موجودی:
      {" "}{formatToman(profile.wallet_balance ?? 0)} · قابل برداشت از کیف پول:
      {" "}{formatToman(Math.min(chosen.outstanding_total, profile.wallet_balance ?? 0))}</p>
      <p>تخفیف قبلی: {formatToman(chosen.discount_total)}</p>
      <form className="admin-settlement-form" onSubmit={settle}><MoneyField id="settle-amount"
        label="برداشت از کیف پول (تومان)" value={settleAmount}
        onValueChange={setSettleAmount} placeholder="۰" />
        <MoneyField id="discount-amount" label="تخفیف (تومان)" value={discountAmount}
          onValueChange={setDiscountAmount} placeholder="۰" />
        {Number(discountAmount) > 0 && <Field id="discount-reason" label="دلیل تخفیف"
          value={discountReason} onChange={(event) => setDiscountReason(event.target.value)}
          maxLength={500} required />}
        <Button type="submit" className="primary admin-settlement-confirm"
          disabled={busy || !canSettle}
          title="ثبت تسویه و تخفیف" aria-label="ثبت تسویه و تخفیف">
          {busy ? "…" : "✓"}</Button></form>
      <SettlementOperations registrationId={chosen.id} revision={revision}
        onChanged={onChanged} /></>}
    </section></div>
  </Card>;
}
