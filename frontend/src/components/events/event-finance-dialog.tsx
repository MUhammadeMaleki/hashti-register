"use client";

import { useEffect, useRef, useState } from "react";
import { EventSettlement } from "@/components/events/event-settlement";
import { SettlementOperations } from "@/components/guests/settlement-operations";
import { formatToman } from "@/lib/format";
import type { EventRegistration } from "@/lib/registrations";
import styles from "./event-finance-dialog.module.css";

export function EventFinanceDialog({ row, revision, onChanged, onDismiss }: {
  row: EventRegistration; revision: number; onChanged: () => void; onDismiss: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<"settle" | "cancel">(row.debt > 0 ? "settle" : "cancel");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return <dialog ref={dialogRef} className={styles.dialog} dir="rtl"
    aria-labelledby="event-finance-title" onClose={onDismiss}
    onClick={(event) => {
      if (event.target === event.currentTarget) dialogRef.current?.close();
    }}>
    <div className={styles.header}>
      <div><span className={styles.kicker}>حساب همین هشتی</span>
        <h3 id="event-finance-title">امور مالی {row.first_name} {row.last_name}</h3></div>
      <button type="button" className={styles.close} aria-label="بستن پنجره"
        onClick={() => dialogRef.current?.close()}>
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M5 5 19 19M19 5 5 19" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </div>
    <div className={styles.summary}>
      <div><small>بدهی این هشتی</small><strong>{formatToman(row.debt)}</strong></div>
      <div><small>موجودی کیف پول</small><strong>{formatToman(row.wallet_balance)}</strong></div>
      <div><small>تسویه و تخفیف فعال</small><strong>
        {formatToman(row.active_settlements + row.active_discounts)}</strong></div>
    </div>
    <div className={styles.tabs} role="tablist" aria-label="عملیات مالی">
      <button type="button" role="tab" id="event-finance-settle-tab"
        aria-selected={tab === "settle"} aria-controls="event-finance-settle-panel"
        onClick={() => { setTab("settle"); setNotice(""); }}>ثبت تسویه</button>
      <button type="button" role="tab" id="event-finance-cancel-tab"
        aria-selected={tab === "cancel"} aria-controls="event-finance-cancel-panel"
        onClick={() => { setTab("cancel"); setNotice(""); }}>لغو تسویه</button>
    </div>
    {notice && <p className="alert success" role="status">{notice}</p>}
    <div role="tabpanel" id="event-finance-settle-panel"
      aria-labelledby="event-finance-settle-tab" hidden={tab !== "settle"}>
      {tab === "settle" && (row.debt > 0 ? <EventSettlement row={row} onChanged={() => {
        onChanged(); setNotice("تسویه ثبت شد.");
      }} /> : <p className={styles.empty}>این هشتی بدهیِ تسویه‌نشده ندارد.</p>)}
    </div>
    <div role="tabpanel" id="event-finance-cancel-panel"
      aria-labelledby="event-finance-cancel-tab" hidden={tab !== "cancel"}>
      {tab === "cancel" && <SettlementOperations registrationId={row.id}
        revision={revision} onChanged={onChanged} />}
    </div>
  </dialog>;
}
