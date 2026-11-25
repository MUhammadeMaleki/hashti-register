"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Field, MoneyField } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { registrationsApi, type Charge, type EventRegistration } from "@/lib/registrations";
import styles from "./event-orders.module.css";

export function EventOrders({ row, cancelled, refresh, onChanged, onDismiss }: {
  row: EventRegistration; cancelled: boolean; refresh: number;
  onChanged: () => void; onDismiss: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const [charges, setCharges] = useState<Charge[]>([]);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    registrationsApi.charges(row.id).then((result) => {
      if (active) { setCharges(result); setError(""); }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [row.id, refresh, revision]);

  function reset() { setEditing(null); setDescription(""); setAmount(""); }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount);
    if (!description.trim() || !Number.isSafeInteger(value) || value <= 0) {
      setError("شرح و مبلغ صحیحِ مثبت را وارد کنید."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      if (editing === null) await registrationsApi.createOrder(row.id, description.trim(), value);
      else await registrationsApi.updateOrder(row.id, editing, description.trim(), value);
      setNotice(editing === null ? "سفارش ثبت شد." : "سفارش ویرایش شد.");
      reset(); setRevision((previous) => previous + 1); onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  async function cancel(id: number) {
    if (!window.confirm("این سفارش لغو شود؟")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await registrationsApi.cancelOrder(row.id, id);
      setNotice("سفارش لغو شد.");
      reset(); setRevision((previous) => previous + 1); onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  const canCreate = !cancelled && row.status === "active" &&
    (row.attendance === "present" || row.attendance === "absent_forfeited");
  const canEdit = !cancelled && row.status === "active";
  const active = charges.filter((charge) => !charge.is_cancelled);
  const past = charges.filter((charge) => charge.is_cancelled);
  const entry = active.filter((charge) => charge.type === "entry");
  const orders = active.filter((charge) => charge.type === "order");
  const orderTotal = orders.reduce((total, charge) => total + charge.amount, 0);

  return <dialog ref={dialogRef} className={styles.dialog} dir="rtl"
    aria-labelledby="event-orders-title" onClose={onDismiss}
    onClick={(event) => {
      if (event.target === event.currentTarget) dialogRef.current?.close();
    }}>
    <div className={styles.header}>
      <div><span className={styles.kicker}>هزینه‌های همین هشتی</span>
        <h3 id="event-orders-title">سفارش‌های {row.first_name} {row.last_name}</h3></div>
      <button type="button" className={styles.close} aria-label="بستن پنجره"
        onClick={() => dialogRef.current?.close()}>
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M5 5 19 19M19 5 5 19" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </div>
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    {loading ? <p className={styles.empty} role="status">در حال دریافت سفارش‌ها…</p> : <>
      <div className={styles.summary}>
        <div><small>ورودی</small><strong>{formatToman(entry.reduce((total, charge) => total + charge.amount, 0))}</strong></div>
        <div><small>سفارش‌های فعال</small><strong>{formatToman(orderTotal)}</strong></div>
      </div>
      <div className={styles.listHeading}><strong>هزینه‌ها و سفارش‌های فعال</strong>
        <span>{active.length.toLocaleString("fa-IR")} مورد</span></div>
      {active.length === 0 && <p className={styles.empty}>هنوز هزینه‌ای ثبت نشده است.</p>}
      <div className={styles.list}>{active.map((charge) => <div className={styles.item} key={charge.id}>
        <div className={styles.itemMain}>
          <span className={charge.type === "entry" ? styles.entryTag : styles.orderTag}>
            {charge.type === "entry" ? "ورودی" : "سفارش"}</span>
          <strong>{charge.description}</strong>
          <span className={styles.amount}>{formatToman(charge.amount)}</span>
        </div>
        {charge.type === "order" && canEdit && <div className={styles.itemActions}>
          <Button type="button" className="secondary" disabled={busy} onClick={() => {
            setEditing(charge.id); setDescription(charge.description);
            setAmount(String(charge.amount)); setNotice("");
            requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
          }}>ویرایش</Button>
          <Button type="button" className="secondary" disabled={busy}
            onClick={() => cancel(charge.id)}>لغو</Button>
        </div>}
      </div>)}</div>
      {past.length > 0 && <details className={styles.history}>
        <summary>سوابق لغوشده <span>{past.length.toLocaleString("fa-IR")}</span></summary>
        <div className={styles.list}>{past.map((charge) => <div className={styles.pastItem} key={charge.id}>
          <span>{charge.type === "entry" ? "ورودی" : "سفارش"} · {charge.description}</span>
          <strong>{formatToman(charge.amount)}</strong>
        </div>)}</div>
      </details>}
    </>}
    {(canCreate || (editing !== null && canEdit)) &&
    <form ref={formRef} onSubmit={save} className={styles.form}>
      <div className={styles.formHeading}><strong>{editing === null ? "افزودن سفارش" : "ویرایش سفارش"}</strong>
        {editing !== null && <Button type="button" className="secondary" disabled={busy}
          onClick={reset}>انصراف</Button>}</div>
      <div className={styles.fields}>
        <Field id={`order-description-${row.id}`} label="شرح سفارش"
          value={description} onChange={(event) => setDescription(event.target.value)} required />
        <MoneyField id={`order-amount-${row.id}`} label="مبلغ (تومان)"
          value={amount} onValueChange={setAmount} required />
      </div>
      <Button type="submit" className={`primary ${styles.submit}`} disabled={busy}>
        {editing === null ? "ثبت سفارش" : "ذخیره سفارش"}</Button>
    </form>}
    {row.attendance === "pending" && <p className={styles.hint}>تا تعیین حضور، ثبت سفارش مجاز نیست.</p>}
  </dialog>;
}
