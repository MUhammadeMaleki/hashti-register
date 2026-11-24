"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { registrationsApi, type Charge, type EventRegistration } from "@/lib/registrations";

export function EventOrders({ row, cancelled, refresh, onChanged }: {
  row: EventRegistration; cancelled: boolean; refresh: number; onChanged: () => void;
}) {
  const [charges, setCharges] = useState<Charge[]>([]);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    registrationsApi.charges(row.id).then((result) => {
      if (active) { setCharges(result); setError(""); }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, [row.id, refresh, revision]);

  function reset() { setEditing(null); setDescription(""); setAmount(""); }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount);
    if (!description.trim() || !Number.isSafeInteger(value) || value <= 0) {
      setError("شرح و مبلغ صحیحِ مثبت را وارد کنید."); return;
    }
    setBusy(true); setError("");
    try {
      if (editing === null) await registrationsApi.createOrder(row.id, description.trim(), value);
      else await registrationsApi.updateOrder(row.id, editing, description.trim(), value);
      reset(); setRevision((previous) => previous + 1); onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  async function cancel(id: number) {
    if (!window.confirm("این سفارش لغو شود؟")) return;
    setBusy(true); setError("");
    try {
      await registrationsApi.cancelOrder(row.id, id);
      reset(); setRevision((previous) => previous + 1); onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  const canCreate = !cancelled && row.status === "active" &&
    (row.attendance === "present" || row.attendance === "absent_forfeited");
  const canEdit = !cancelled && row.status === "active";
  return <div className="form-stack">
    <strong>هزینه‌ها و سفارش‌های {row.first_name} {row.last_name}</strong>
    {error && <p className="alert error" role="alert">{error}</p>}
    {charges.length === 0 && <p className="muted">هنوز هزینه‌ای ثبت نشده است.</p>}
    <div className="table-scroll"><table><thead><tr><th>نوع</th><th>شرح</th><th>مبلغ</th>
      <th>وضعیت</th><th>عملیات</th></tr></thead><tbody>{charges.map((charge) =>
      <tr key={charge.id}><td>{charge.type === "entry" ? "ورودی" : "سفارش"}</td>
        <td>{charge.description}</td><td>{formatToman(charge.amount)}</td>
        <td>{charge.is_cancelled ? "لغوشده" : "فعال"}</td><td>
        {charge.type === "order" && !charge.is_cancelled && canEdit && <>
          <Button type="button" className="secondary" disabled={busy} onClick={() => {
            setEditing(charge.id); setDescription(charge.description);
            setAmount(String(charge.amount)); }}>ویرایش</Button>{" "}
          <Button type="button" className="secondary" disabled={busy}
            onClick={() => cancel(charge.id)}>لغو</Button></>}</td></tr>)}</tbody></table></div>
    {canCreate && <form onSubmit={save} className="form-stack">
      <div className="field-row"><Field id={`order-description-${row.id}`} label="شرح سفارش"
        value={description} onChange={(event) => setDescription(event.target.value)} required />
        <Field id={`order-amount-${row.id}`} label="مبلغ (تومان)" type="number" min={1}
          value={amount} onChange={(event) => setAmount(event.target.value)} required /></div>
      <div><Button type="submit" className="primary" disabled={busy}>
        {editing === null ? "ثبت سفارش" : "ذخیره سفارش"}</Button>{" "}
        {editing !== null && <Button type="button" className="secondary" onClick={reset}>
          انصراف</Button>}</div></form>}
    {row.attendance === "pending" && <p className="muted">تا تعیین حضور، ثبت سفارش مجاز نیست.</p>}
  </div>;
}
