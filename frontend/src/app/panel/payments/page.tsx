"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { AppShell } from "@/components/app-shell";
import { Button, Card } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatJalali, formatToman, persianDigits } from "@/lib/format";
import { paymentsApi, type AdminPayment, type Payment } from "@/lib/payments";

const labels = { pending: "در انتظار بررسی", approved: "تأییدشده", rejected: "ردشده" };

function ReceiptThumbnail({ payment }: { payment: AdminPayment }) {
  const image = <Image
    src={payment.has_image ? `/api/admin/payments/${payment.id}/receipt` : "/receipt-tracking.svg"}
    alt={payment.has_image ? `تصویر رسید ${payment.guest_name}` : "تصویر نمادینِ ثبت با کد پیگیری"}
    width={76} height={76} unoptimized
  />;
  return <div className="payment-thumbnail">
    {payment.has_image ? <a href={`/receipt/${payment.id}?viewer=admin`}
      target="_blank" rel="noopener noreferrer" aria-label={`نمایش تصویر رسید ${payment.guest_name}`}>
      {image}</a> : image}
    <span>{payment.has_image ? "تصویر رسید" : "کد پیگیری"}</span>
  </div>;
}

export default function PaymentsPage() {
  const [status, setStatus] = useState<Payment["status"]>("pending");
  const [items, setItems] = useState<AdminPayment[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<AdminPayment | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    paymentsApi.adminList(status).then((result) => {
      if (active) { setItems(result.items); setTotal(result.total); }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, [status]);

  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get("receipt"));
    if (!Number.isSafeInteger(id) || id < 1) return;
    let active = true;
    paymentsApi.adminDetail(id).then((payment) => {
      if (active) setSelected(payment);
    }).catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, []);

  async function loadMore() {
    setBusy(true); setError("");
    try {
      const result = await paymentsApi.adminList(status, items.length);
      setItems((previous) => [...previous, ...result.items]);
      setTotal(result.total);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function selectPayment(id: number) {
    setError("");
    try { setSelected(await paymentsApi.adminDetail(id)); setReason(""); }
    catch (caught) { setError(errorMessage(caught)); }
  }

  async function review(approve: boolean) {
    if (!selected || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await (approve ? paymentsApi.approve(selected.id) : paymentsApi.reject(selected.id, reason));
      setItems((previous) => previous.filter((item) => item.id !== selected.id));
      setTotal((previous) => Math.max(0, previous - 1));
      setSelected(null); setReason("");
      setNotice(approve ? "رسید تأیید و کیف پول شارژ شد؛ بدهی رویداد تسویه نشده است." :
        "رسید رد شد و در تاریخچه باقی ماند.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <AppShell kind="user"><div className="editor-stack">
    <div className="welcome-band"><div><span className="eyebrow">امور مالی</span>
      <h2>بررسی رسیدها</h2><p>تأیید رسید فقط کیف پول مهمان را شارژ می‌کند.</p></div></div>
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    <Card title="صف رسیدها"><div className="field-row">
      {(["pending", "approved", "rejected"] as const).map((value) =>
        <Button key={value} type="button" className={status === value ? "" : "secondary"}
          onClick={() => { setStatus(value); setSelected(null); setError(""); }}>{labels[value]}</Button>)}
    </div>
      {items.map((item) => <div className="guest-history-item payment-list-item" key={item.id}>
        <ReceiptThumbnail payment={item} />
        <div className="payment-list-details">
          <p>{item.guest_name} · {formatToman(item.amount)} · {item.event_title ?? "شارژ مستقل"}</p>
          <p className="muted">{formatJalali(item.created_at)} · {labels[item.status]}</p>
        </div>
        <Button type="button" className="secondary" onClick={() => selectPayment(item.id)}>
          جزئیات و بررسی</Button>
      </div>)}
      {!items.length && <p className="muted">رسیدی در این وضعیت دیده نمی‌شود.</p>}
      {items.length < total && <Button type="button" className="secondary" disabled={busy}
        onClick={loadMore}>نمایش رسیدهای بیشتر</Button>}
    </Card>
    {selected && <section className="card payment-detail" aria-labelledby="payment-detail-title">
      <div className="payment-detail-header">
        <div><span className="eyebrow">جزئیات پرداخت</span>
          <h2 id="payment-detail-title">رسید شمارهٔ {persianDigits(String(selected.id))}</h2></div>
        <span className={`payment-status payment-status-${selected.status}`}>{labels[selected.status]}</span>
      </div>
      <div className="payment-detail-body">
        <div className="payment-detail-preview"><ReceiptThumbnail payment={selected} />
          {selected.has_image && <span className="muted">برای دیدن تصویر کامل، روی آن بزنید.</span>}</div>
        <dl className="payment-detail-facts">
          <div className="payment-detail-amount"><dt>مبلغ واریز</dt><dd>{formatToman(selected.amount)}</dd></div>
          <div><dt>هشتی‌نشین</dt><dd>{selected.guest_name}</dd></div>
          <div><dt>هشتی</dt><dd>{selected.event_title ?? "شارژ مستقل کیف پول"}</dd></div>
          <div><dt>زمان ثبت</dt><dd>{formatJalali(selected.created_at)}</dd></div>
          {selected.tracking_code && <div><dt>کد پیگیری</dt>
            <dd dir="ltr">{persianDigits(selected.tracking_code)}</dd></div>}
          {selected.reviewed_at && <div><dt>زمان بررسی</dt><dd>{formatJalali(selected.reviewed_at)}</dd></div>}
          {selected.reject_reason && <div className="payment-detail-reason"><dt>دلیل رد</dt>
            <dd>{selected.reject_reason}</dd></div>}
        </dl>
      </div>
      {selected.status === "pending" && <div className="editor-stack payment-detail-review">
        <div className="field"><label htmlFor="reject-reason">دلیل رد (اختیاری)</label>
          <textarea id="reject-reason" maxLength={2000} value={reason}
            onChange={(event) => setReason(event.target.value)} /></div>
        <div className="field-row"><Button type="button" disabled={busy} onClick={() => review(true)}>
          تأیید و شارژ کیف پول</Button>
          <Button type="button" className="secondary" disabled={busy} onClick={() => review(false)}>
            رد رسید</Button></div>
      </div>}
    </section>}
  </div></AppShell>;
}
