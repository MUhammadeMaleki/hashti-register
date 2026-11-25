"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, Field, MoneyField } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { guestsApi, type GuestProfile } from "@/lib/guests";
import styles from "./guest-profile.module.css";

type Settlement = { id: number; amount: number; active_amount: number; created_at: string };

export function GuestFinance({ profile, onChanged }: {
  profile: GuestProfile; onChanged: () => Promise<void>;
}) {
  const [direction, setDirection] = useState<"increase" | "decrease">("increase");
  const [adjustAmount, setAdjustAmount] = useState("");
  const [note, setNote] = useState("");
  const [registrationId, setRegistrationId] = useState<number | null>(null);
  const [settleAmount, setSettleAmount] = useState("");
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [refundId, setRefundId] = useState<number | null>(null);
  const [refundAmount, setRefundAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const active = profile.registrations.filter((row) => row.status === "active");
  const chosen = active.find((row) => row.id === registrationId);

  useEffect(() => {
    if (registrationId === null) return;
    let mounted = true;
    guestsApi.settlements(registrationId).then((rows) => {
      if (mounted) setSettlements(rows);
    }).catch((caught) => { if (mounted) setError(errorMessage(caught)); });
    return () => { mounted = false; };
  }, [registrationId, revision]);

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
    if (!Number.isSafeInteger(value) || value <= 0 ||
        value > Math.min(chosen.outstanding_total, profile.wallet_balance ?? 0)) {
      setError("مبلغ تسویه باید مثبت و حداکثر برابر بدهی و موجودی باشد."); return;
    }
    if (await run(() => guestsApi.settle(chosen.id, value), "تسویهٔ هشتی ثبت شد."))
      setSettleAmount("");
  }

  async function refund(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selected = settlements.find((item) => item.id === refundId);
    const value = Number(refundAmount);
    if (!selected || !Number.isSafeInteger(value) || value <= 0 ||
        value > selected.active_amount || !reason.trim()) {
      setError("مبلغ برگشت باید در سقف تسویهٔ فعال و همراه دلیل باشد."); return;
    }
    if (await run(() => guestsApi.refund(selected.id, value, reason.trim()),
      "برگشت به تسویهٔ اصلی متصل و ثبت شد.")) {
      setRefundAmount(""); setReason("");
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
        setRefundId(null); setSettlements([]);
      }}><option value="">انتخاب هشتی</option>{active.map((row) =>
        <option key={row.id} value={row.id}>هشتی {row.event.event_number.toLocaleString("fa-IR")} · {row.event.title}</option>)}</select>
    </div>
    {chosen && <><p>بدهی: {formatToman(chosen.outstanding_total)} · موجودی:
      {" "}{formatToman(profile.wallet_balance ?? 0)} · قابل تسویه:
      {" "}{formatToman(Math.min(chosen.outstanding_total, profile.wallet_balance ?? 0))}</p>
      <form className="form-stack" onSubmit={settle}><MoneyField id="settle-amount"
        label="مبلغ تسویه (تومان)" value={settleAmount}
        onValueChange={setSettleAmount} required />
        <Button type="submit" className="secondary" disabled={busy || chosen.event.is_cancelled ||
          Math.min(chosen.outstanding_total, profile.wallet_balance ?? 0) <= 0}>
          تسویه با کیف پول</Button></form>
      <h3>برگشت تسویه</h3><div className="field"><label htmlFor="refund-settlement">تسویهٔ اصلی</label>
        <select id="refund-settlement" value={refundId ?? ""} onChange={(event) =>
          setRefundId(event.target.value ? Number(event.target.value) : null)}>
          <option value="">انتخاب تسویه</option>{settlements.filter((item) => item.active_amount > 0)
            .map((item) => <option value={item.id} key={item.id}>#{item.id.toLocaleString("fa-IR")} · فعال:
              {" "}{formatToman(item.active_amount)}</option>)}</select></div>
      {refundId !== null && <form className="form-stack" onSubmit={refund}>
        <MoneyField id="refund-amount" label="مبلغ برگشت (تومان)"
          value={refundAmount} onValueChange={setRefundAmount} required />
        <Field id="refund-reason" label="دلیل برگشت" value={reason}
          onChange={(event) => setReason(event.target.value)} required />
        <Button type="submit" className="secondary" disabled={busy}>ثبت برگشت</Button>
      </form>}</>}
    </section></div>
  </Card>;
}
