"use client";

import { useState, type FormEvent } from "react";
import { Button, Field, MoneyField } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { guestsApi } from "@/lib/guests";
import type { EventRegistration } from "@/lib/registrations";

export function EventSettlement({ row, onChanged }: {
  row: EventRegistration; onChanged: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [discount, setDiscount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const available = Math.min(row.debt, row.wallet_balance);
  const walletValue = Number(amount);
  const discountValue = Number(discount);
  const canSubmit = Number.isSafeInteger(walletValue) && Number.isSafeInteger(discountValue) &&
    walletValue >= 0 && discountValue >= 0 && walletValue + discountValue > 0 &&
    walletValue <= row.wallet_balance && walletValue + discountValue <= row.debt &&
    (discountValue === 0 || !!reason.trim());

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount);
    const discountValue = Number(discount);
    if (!Number.isSafeInteger(value) || !Number.isSafeInteger(discountValue) ||
      value < 0 || discountValue < 0 || value + discountValue <= 0 ||
      value > row.wallet_balance || value + discountValue > row.debt ||
      (discountValue > 0 && !reason.trim())) {
      setError("مجموع برداشت و تخفیف نباید از بدهی بیشتر شود؛ تخفیف دلیل می‌خواهد.");
      return;
    }
    setBusy(true); setError("");
    try {
      await guestsApi.settle(row.id, value, discountValue, reason.trim());
      setAmount(""); setDiscount(""); setReason("");
      onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="event-settlement">
    <strong>تسویهٔ {row.first_name} {row.last_name} در همین رویداد</strong>
    <p>بدهی: {formatToman(row.debt)} · موجودی کیف پول: {formatToman(row.wallet_balance)}
      {" "}· قابل برداشت: {formatToman(available)} · تخفیف قبلی: {formatToman(row.active_discounts)}</p>
    <form className="admin-settlement-form" onSubmit={submit}>
        <MoneyField id={`event-settlement-${row.id}`} label="برداشت از کیف پول (تومان)"
          value={amount} onValueChange={setAmount} placeholder="۰" />
        <MoneyField id={`event-discount-${row.id}`} label="تخفیف (تومان)"
          value={discount} onValueChange={setDiscount} placeholder="۰" />
        {Number(discount) > 0 && <Field id={`event-discount-reason-${row.id}`}
          label="دلیل تخفیف" value={reason}
          onChange={(event) => setReason(event.target.value)} maxLength={500} required />}
        <Button type="submit" className="primary admin-settlement-confirm" disabled={busy || !canSubmit}
          title="ثبت تسویه و تخفیف" aria-label="ثبت تسویه و تخفیف">
          {busy ? "…" : "✓"}</Button>
      </form>
    {error && <p className="alert error" role="alert">{error}</p>}
  </div>;
}
