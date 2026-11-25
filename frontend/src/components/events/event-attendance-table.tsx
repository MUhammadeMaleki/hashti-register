"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { Button, Card } from "@/components/ui";
import { EventOrders } from "@/components/events/event-orders";
import { EventSettlement } from "@/components/events/event-settlement";
import { errorMessage } from "@/lib/api";
import { formatToman } from "@/lib/format";
import { registrationsApi, type Attendance, type EventRegistration } from "@/lib/registrations";
import styles from "./event-attendance-table.module.css";

const labels: Record<Attendance, string> = {
  pending: "نامشخص", present: "حاضر", absent_kept: "غایب، بدون هزینه",
  absent_forfeited: "غایب، با هزینه",
};

export function EventAttendanceTable({ eventId, cancelled, registrationOpen, refresh }: {
  eventId: number; cancelled: boolean; registrationOpen: boolean; refresh: number;
}) {
  const [rows, setRows] = useState<EventRegistration[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [ordersId, setOrdersId] = useState<number | null>(null);
  const [settlementId, setSettlementId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    registrationsApi.eventList(eventId, offset).then((page) => {
      if (!active) return;
      setRows(page.items); setTotal(page.total); setError("");
    }).catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [eventId, offset, refresh, revision]);

  async function change(registrationId: number, attendance: Attendance) {
    if (busyId !== null) return;
    setBusyId(registrationId); setError(""); setNotice("");
    try {
      await registrationsApi.setAttendance(registrationId, attendance, crypto.randomUUID());
      setNotice("وضعیت حضور ذخیره شد.");
      setRevision((value) => value + 1);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusyId(null); }
  }

  async function changeRegistration(row: EventRegistration) {
    if (busyId !== null) return;
    const reactivate = row.status === "cancelled";
    if (!reactivate && !window.confirm(
      `ثبت‌نام ${row.first_name} ${row.last_name} لغو شود و تسویه‌هایش برگردد؟`
    )) return;
    setBusyId(row.id); setError(""); setNotice("");
    try {
      if (reactivate) {
        await registrationsApi.reactivate(row.id);
        setNotice("همان ثبت‌نام با حضور نامشخص دوباره فعال شد؛ هزینه‌ای ایجاد نشد.");
      } else {
        const result = await registrationsApi.cancel(row.id);
        setNotice(`${result.refunded_total} تومان به کیف پول مهمان برگشت داده شد.`);
      }
      setRevision((value) => value + 1);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusyId(null); }
  }

  return <div className={styles.panel}><Card title="هشتی‌نشین‌ها و حضور">
    <p className="muted">تغییر حضور ممکن است هزینهٔ ورودی ایجاد کند یا اعتبار تسویه‌شده را برگرداند.</p>
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    {loading && <p role="status">در حال دریافت مهمان‌ها…</p>}
    <div className={`table-scroll ${styles.tableScroll}`}><table className={styles.table}><thead><tr><th>هشتی‌نشین</th><th>موبایل</th>
      <th>ثبت‌نام</th><th>حضور</th><th>هزینهٔ فعال</th><th>تسویه</th>
      <th>بدهی</th><th>اعتبار</th><th>رسید همین هشتی</th><th>سفارش‌ها</th><th>عملیات</th></tr></thead><tbody>
      {rows.map((row) => <Fragment key={row.id}><tr>
        <td><Link className={`text-link ${styles.guestName}`} href={`/panel/guests/${row.guest_id}`}>
          {row.first_name} {row.last_name}</Link></td><td dir="ltr">{row.phone}</td>
        <td>{row.status === "active" ? "فعال" : "لغوشده"}</td>
        <td><select className={styles.attendanceSelect} aria-label={`حضور ${row.first_name} ${row.last_name}`}
          value={row.attendance} disabled={cancelled || row.status !== "active" || busyId !== null}
          onChange={(event) => change(row.id, event.target.value as Attendance)}>
          {row.attendance === "pending" && <option value="pending">{labels.pending}</option>}
          <option value="present">{labels.present}</option>
          <option value="absent_kept">{labels.absent_kept}</option>
          <option value="absent_forfeited">{labels.absent_forfeited}</option>
        </select></td>
        <td>{formatToman(row.active_charge_total)}</td>
        <td>{formatToman(row.active_settlements)}</td><td>{formatToman(row.debt)}</td>
        <td>{formatToman(row.wallet_balance)}</td>
        <td>{row.event_payments.length ? <div className="event-payment-list">
          {row.event_payments.map((payment) => <Link key={payment.id}
            href={`/panel/payments?receipt=${payment.id}`} className={`event-payment-tag is-${payment.status}`}
            title="رسید مرتبط با این هشتی؛ به‌معنی تسویهٔ بدهی نیست">
            {formatToman(payment.amount)} · {payment.status === "pending" ? "در انتظار بررسی" :
              payment.status === "approved" ? "تأییدشده" : "ردشده"}</Link>)}
        </div> : <span className="muted">رسیدی ثبت نشده</span>}</td>
        <td><Button type="button" className="secondary" onClick={() =>
          setOrdersId((value) => value === row.id ? null : row.id)}>
          {ordersId === row.id ? "بستن" : "مشاهده"}</Button></td>
        <td><div className={styles.actions}><Button type="button" className="secondary"
          disabled={cancelled || row.status !== "active" || row.debt <= 0 || busyId !== null}
          onClick={() => setSettlementId((value) => value === row.id ? null : row.id)}>
          {settlementId === row.id ? "بستن تسویه" : "تسویه"}
        </Button>{row.status === "active" ? <Button type="button" className="danger-button"
          disabled={cancelled || busyId !== null} onClick={() => changeRegistration(row)}>
          لغو ثبت‌نام</Button> : <Button type="button" className="secondary"
          disabled={cancelled || !registrationOpen || busyId !== null}
          onClick={() => changeRegistration(row)}>فعال‌سازی مجدد</Button>}</div></td>
      </tr>{ordersId === row.id && <tr><td colSpan={11}>
        <EventOrders row={row} cancelled={cancelled} refresh={revision}
          onChanged={() => setRevision((value) => value + 1)} />
      </td></tr>}{settlementId === row.id && !cancelled && row.status === "active" &&
      <tr><td colSpan={11}>
        <EventSettlement row={row} onChanged={() => {
          setSettlementId(null); setNotice("تسویهٔ رویداد ثبت شد.");
          setRevision((value) => value + 1);
        }} />
      </td></tr>}</Fragment>)}</tbody></table></div>
    {!loading && rows.length === 0 && <p className="muted">هنوز مهمانی ثبت‌نام نکرده است.</p>}
    <div className="pagination"><span>{total.toLocaleString("fa-IR")} ثبت‌نام</span>
      {offset > 0 && <Button type="button" className="secondary" onClick={() => {
        setLoading(true); setOffset(Math.max(0, offset - 50)); }}>قبلی</Button>}
      {offset + 50 < total && <Button type="button" className="secondary" onClick={() => {
        setLoading(true); setOffset(offset + 50); }}>بعدی</Button>}
      <Button type="button" className="secondary" onClick={() => {
        setLoading(true); setRevision((value) => value + 1); }}>تازه‌سازی</Button></div>
  </Card></div>;
}
