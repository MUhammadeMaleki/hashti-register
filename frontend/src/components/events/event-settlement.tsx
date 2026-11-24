"use client";

import { useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { guestsApi } from "@/lib/guests";
import type { EventRegistration } from "@/lib/registrations";

export function EventSettlement({ row, onChanged }: {
  row: EventRegistration; onChanged: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const available = Math.min(row.debt, row.wallet_balance);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount);
    if (!Number.isSafeInteger(value) || value <= 0 || value > available) {
      setError("مبلغ باید مثبت و حداکثر برابر بدهی و موجودی کیف پول باشد.");
      return;
    }
    setBusy(true); setError("");
    try {
      await guestsApi.settle(row.id, value);
      setAmount("");
      onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="event-settlement">
    <strong>تسویهٔ {row.first_name} {row.last_name} در همین رویداد</strong>
    <p>بدهی: {formatToman(row.debt)} · موجودی کیف پول: {formatToman(row.wallet_balance)}
      {" "}· قابل تسویه: {formatToman(available)}</p>
    {available <= 0 ? <p className="muted">برای تسویه، ابتدا کیف پول مخاطب باید شارژ شود.</p> :
      <form className="field-row" onSubmit={submit}>
        <Field id={`event-settlement-${row.id}`} label="مبلغ تسویه (تومان)"
          type="number" min={1} max={available} value={amount}
          onChange={(event) => setAmount(event.target.value)} required />
        <Button type="submit" className="secondary" disabled={busy}>
          {busy ? "در حال ثبت…" : "تسویه با کیف پول"}</Button>
      </form>}
    {error && <p className="alert error" role="alert">{error}</p>}
  </div>;
}
