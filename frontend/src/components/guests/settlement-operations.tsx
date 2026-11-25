"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatJalali, formatToman } from "@/lib/format";
import { guestsApi, type SettlementOperation } from "@/lib/guests";
import styles from "./settlement-operations.module.css";

export function SettlementOperations({ registrationId, revision, onChanged }: {
  registrationId: number; revision: number; onChanged: () => void | Promise<void>;
}) {
  const [operations, setOperations] = useState<SettlementOperation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [localRevision, setLocalRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    guestsApi.settlementOperations(registrationId).then((rows) => {
      if (active) { setOperations(rows); setError(""); }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [registrationId, revision, localRevision]);

  async function cancel(event: FormEvent<HTMLFormElement>, operation: SettlementOperation) {
    event.preventDefault();
    if (busy || !reason.trim() || !window.confirm(
      "این نوبت تسویه لغو شود؟ برداشتِ فعال به کیف پول برمی‌گردد و تخفیفِ فعال خنثی می‌شود."
    )) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await guestsApi.cancelSettlement(operation.id, reason.trim());
      setSelectedId(null); setReason("");
      await onChanged();
      setLocalRevision((value) => value + 1);
      setNotice("نوبت تسویه لغو شد؛ برداشت و تخفیفِ فعال آن خنثی شدند.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className={styles.root}>
    <h3>نوبت‌های تسویه</h3>
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    {loading && <p className="muted" role="status">در حال دریافت تسویه‌ها…</p>}
    {!loading && !error && !operations.length &&
      <p className="muted">تسویه‌ای برای این هشتی ثبت نشده است.</p>}
    {operations.map((operation) => {
      const active = operation.active_amount + operation.active_discount_amount > 0;
      return <div className={styles.operation} key={operation.id}>
        <div className={styles.details}>
          <strong>تسویهٔ {formatJalali(operation.created_at)}</strong>
          <span>برداشت: {formatToman(operation.amount)} · تخفیف: {formatToman(operation.discount_amount)}</span>
          <span>{active ? `فعال: ${formatToman(operation.active_amount)} برداشت + ${formatToman(operation.active_discount_amount)} تخفیف` : "لغوشده یا برگشت‌خورده"}</span>
        </div>
        {active && <Button type="button" className="secondary" disabled={busy}
          onClick={() => { setSelectedId(selectedId === operation.id ? null : operation.id); setReason(""); }}>
          {selectedId === operation.id ? "بستن" : "لغو تسویه"}
        </Button>}
        {selectedId === operation.id && active && <form className={styles.form}
          onSubmit={(event) => cancel(event, operation)}>
          <Field id={`cancel-settlement-reason-${registrationId}-${operation.id}`}
            label="دلیل لغو تسویه" value={reason} maxLength={500} required
            onChange={(event) => setReason(event.target.value)} />
          <Button type="submit" className="danger-button" disabled={busy || !reason.trim()}>
            تأیید لغو تسویه</Button>
        </form>}
      </div>;
    })}
  </div>;
}
