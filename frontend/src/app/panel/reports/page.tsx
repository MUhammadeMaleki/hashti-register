"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, Card, Field } from "@/components/ui";
import { useSession } from "@/hooks/use-session";
import { errorMessage } from "@/lib/api";
import { formatJalali, formatToman, isoToJalali, jalaliToIso, latinDigits,
  persianDigits } from "@/lib/format";
import { reportsApi, type Charts, type EventReport, type FinancialGuest,
  type GuestReportRow, type Reconciliation, type ReportOptions,
  type ReportPage } from "@/lib/reports";

type Applied = { params: string; eventId: number | null;
  search: string; debtorsOnly: boolean };

function Bars({ rows, empty = "داده‌ای در این بازه ثبت نشده است." }: {
  rows: { label: string; count: number }[]; empty?: string;
}) {
  if (!rows.length || rows.every((row) => row.count === 0)) return <p className="muted">{empty}</p>;
  const maximum = Math.max(...rows.map((row) => row.count), 1);
  return <div className="report-bars">{rows.map((row) => <div className="report-bar" key={row.label}>
    <span>{persianDigits(row.label)}</span><div className="report-bar-track"
      aria-label={`${persianDigits(row.label)}: ${persianDigits(String(row.count))}`}>
      <div style={{ width: `${row.count / maximum * 100}%` }} /></div>
    <strong>{row.count.toLocaleString("fa-IR")}</strong>
  </div>)}</div>;
}

const chartColors = ["#0067a5", "#ff7700", "#45a6c9", "#123e63", "#ffab53", "#72bfd4", "#547c9a", "#e18d67"];

function InterestDonut({ rows }: { rows: { name: string; count: number }[] }) {
  const values = rows.filter((row) => row.count > 0);
  const total = values.reduce((sum, row) => sum + row.count, 0);
  if (!total) return <p className="muted">داده‌ای در این بازه ثبت نشده است.</p>;
  let start = 0;
  const slices = values.map((row, index) => {
    const end = start + row.count / total * 100;
    const slice = `${chartColors[index % chartColors.length]} ${start}% ${end}%`;
    start = end;
    return slice;
  });
  return <div className="report-donut-layout">
    <div className="report-donut" style={{ background: `conic-gradient(${slices.join(",")})` }}
      role="img" aria-label={values.map((row) => `${persianDigits(row.name)}: ${persianDigits(String(row.count))}`).join("، ")}>
      <div><strong>{total.toLocaleString("fa-IR")}</strong><span>علاقه‌مندی ثبت‌شده</span></div>
    </div>
    <ul className="report-donut-legend">{values.map((row, index) =>
      <li key={`${row.name}-${index}`}><span className="report-legend-dot"
        style={{ backgroundColor: chartColors[index % chartColors.length] }} />
        <span>{persianDigits(row.name)}</span><strong>{row.count.toLocaleString("fa-IR")}</strong></li>)}</ul>
  </div>;
}

export default function ReportsPage() {
  const { session } = useSession();
  const [options, setOptions] = useState<ReportOptions | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [eventId, setEventId] = useState("");
  const [search, setSearch] = useState("");
  const [interestId, setInterestId] = useState("");
  const [attendance, setAttendance] = useState("");
  const [guestKind, setGuestKind] = useState("");
  const [financialStatus, setFinancialStatus] = useState("");
  const [minAttendance, setMinAttendance] = useState("");
  const [minAbsence, setMinAbsence] = useState("");
  const [debtorsOnly, setDebtorsOnly] = useState(false);
  const [applied, setApplied] = useState<Applied>({ params: "",
    eventId: null, search: "", debtorsOnly: false });
  const [offset, setOffset] = useState(0);
  const [finance, setFinance] = useState<ReportPage<FinancialGuest> | null>(null);
  const [guests, setGuests] = useState<ReportPage<GuestReportRow> | null>(null);
  const [charts, setCharts] = useState<Charts | null>(null);
  const [eventReport, setEventReport] = useState<EventReport | null>(null);
  const [reconciliation, setReconciliation] = useState<Reconciliation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    let active = true;
    reportsApi.options().then((result) => { if (active) setOptions(result); })
      .catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (session?.role !== "super_admin") return;
    let active = true;
    reportsApi.reconciliation().then((result) => {
      if (active) setReconciliation(result);
    }).catch((caught) => { if (active) setError(errorMessage(caught)); });
    return () => { active = false; };
  }, [session?.role]);
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(applied.params);
    params.set("offset", String(offset));
    const eventRequest = applied.eventId === null ? Promise.resolve(null) :
      reportsApi.event(applied.eventId, applied.search);
    Promise.all([reportsApi.finance(applied.search, applied.debtorsOnly, offset),
      reportsApi.guests(params), reportsApi.charts(new URLSearchParams(applied.params)),
      eventRequest]).then(([financial, guestRows, chartData, eventData]) => {
      if (active) {
        setFinance(financial); setGuests(guestRows); setCharts(chartData);
        setEventReport(eventData); setError("");
      }
    }).catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [applied, offset]);

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const from = dateFrom.trim() ? jalaliToIso(dateFrom) : null;
    const to = dateTo.trim() ? jalaliToIso(dateTo) : null;
    if ((dateFrom.trim() && !from) || (dateTo.trim() && !to) ||
        (from && to && from > to)) {
      setError("بازهٔ تاریخ شمسی معتبر نیست."); return;
    }
    const period = new URLSearchParams();
    if (from) period.set("date_from", from);
    if (to) period.set("date_to", to);
    const params = new URLSearchParams(period);
    if (eventId) params.set("event_id", eventId);
    if (interestId) params.set("interest_tag_id", interestId);
    if (attendance) params.set("attendance", attendance);
    if (guestKind) params.set("guest_kind", guestKind);
    if (financialStatus) params.set("financial_status", financialStatus);
    if (minAttendance) params.set("min_attendance", latinDigits(minAttendance));
    if (minAbsence) params.set("min_absence", latinDigits(minAbsence));
    if (search.trim()) params.set("q", search.trim());
    setLoading(true); setError(""); setOffset(0);
    setApplied({ params: params.toString(),
      eventId: eventId ? Number(eventId) : null, search: search.trim(), debtorsOnly });
    setFiltersOpen(false);
  }

  return <AppShell kind="user"><div className="editor-stack">
    <div className="section-heading"><div><h2>گزارش‌ها</h2>
      <p className="muted">آمار حضور، مطالبات و اعتبار؛ مشاهده برای همهٔ دبیران فعال مجاز است.</p>
    </div></div>
    {error && <p className="alert error" role="alert">{error}</p>}
    <div className={`reports-filter-panel ${filtersOpen ? "is-open" : ""}`}><section className="card">
      <div className="report-filter-heading"><div><span>جست‌وجوی دقیق</span><h2>فیلتر گزارش‌ها</h2></div>
        <button type="button" className="report-filter-toggle" aria-expanded={filtersOpen}
          aria-controls="report-filter-content" onClick={() => setFiltersOpen((open) => !open)}>
          {filtersOpen ? "بستن فیلترها" : "نمایش فیلترها"}<span aria-hidden="true">⌄</span></button></div>
      <div id="report-filter-content" className="report-filter-content"><form className="report-filters" onSubmit={apply}>
      <Field id="report-from" label="از تاریخ (شمسی)" placeholder="۱۴۰۵/۰۹/۰۱"
        value={dateFrom} onChange={(event) => setDateFrom(persianDigits(latinDigits(event.target.value)))} />
      <Field id="report-to" label="تا تاریخ (شمسی)" placeholder="۱۴۰۵/۰۹/۳۰"
        value={dateTo} onChange={(event) => setDateTo(persianDigits(latinDigits(event.target.value)))} />
      <div className="field"><label htmlFor="report-event">هشتی</label><select id="report-event"
        value={eventId} onChange={(event) => setEventId(event.target.value)}>
        <option value="">همهٔ هشتی‌ها</option>{options?.events.map((item) =>
          <option value={item.id} key={item.id}>هشتی {persianDigits(String(item.event_number))} · {persianDigits(item.title)}</option>)}
      </select></div>
      <Field id="report-search" label="جست‌وجوی هشتی‌نشین" value={search}
        onChange={(event) => setSearch(event.target.value)} />
      <div className="field"><label htmlFor="report-attendance">وضعیت حضور</label>
        <select id="report-attendance" value={attendance}
          onChange={(event) => setAttendance(event.target.value)}>
          <option value="">همه</option><option value="present">حاضر</option>
          <option value="pending">نامشخص</option><option value="absent_kept">غایب با حفظ اعتبار</option>
          <option value="absent_forfeited">غایب با سوخت اعتبار</option>
        </select></div>
      <div className="field"><label htmlFor="report-kind">نوع هشتی‌نشین</label>
        <select id="report-kind" value={guestKind} onChange={(event) => setGuestKind(event.target.value)}>
          <option value="">همه</option><option value="new">اولین حضور یا بدون حضور</option>
          <option value="returning">بازگشتی (بیش از یک حضور)</option>
        </select></div>
      <div className="field"><label htmlFor="report-interest">علاقه‌مندی</label>
        <select id="report-interest" value={interestId}
          onChange={(event) => setInterestId(event.target.value)}>
          <option value="">همه</option>{options?.interests.map((item) =>
            <option key={item.id} value={item.id}>{persianDigits(item.name)}</option>)}
        </select></div>
      <div className="field"><label htmlFor="report-financial">وضعیت مالی خالص</label>
        <select id="report-financial" value={financialStatus}
          onChange={(event) => setFinancialStatus(event.target.value)}>
          <option value="">همه</option><option value="debtor">بدهکار</option>
          <option value="credit">دارای اعتبار</option><option value="balanced">تسویه</option>
        </select></div>
      <Field id="report-min-present" label="حداقل حضور" inputMode="numeric" pattern="[۰-۹0-9]*"
        value={minAttendance} onChange={(event) => setMinAttendance(persianDigits(latinDigits(event.target.value).replace(/[^0-9]/g, "")))} />
      <Field id="report-min-absent" label="حداقل غیبت" inputMode="numeric" pattern="[۰-۹0-9]*"
        value={minAbsence} onChange={(event) => setMinAbsence(persianDigits(latinDigits(event.target.value).replace(/[^0-9]/g, "")))} />
      <div className="report-filter-actions"><label className="checkbox-item"><input type="checkbox" checked={debtorsOnly}
        onChange={(event) => setDebtorsOnly(event.target.checked)} />فقط خالص بدهکاران در جدول مالی</label>
        <Button type="submit" className="primary" disabled={loading}>اعمال فیلترها</Button></div>
    </form></div></section></div>
    {loading && <p role="status">در حال محاسبهٔ گزارش…</p>}
    {!loading && eventReport && <Card title={`گزارش مالی هشتی ${persianDigits(String(eventReport.event.event_number))}`}>
      <a className="button secondary" href={`/api/admin/reports/export/events/${applied.eventId}?q=${encodeURIComponent(applied.search)}`}>
        دریافت Excel بدهکاران رویداد</a>
      <div className="report-kpis">
        <p>حاضران: {eventReport.present_count.toLocaleString("fa-IR")}</p>
        <p>ورودی: {formatToman(eventReport.entry_total)}</p>
        <p>سفارش‌ها: {formatToman(eventReport.orders_total)}</p>
        <p>کل هزینه: {formatToman(eventReport.charges_total)}</p>
        <p>تسویه‌شده: {formatToman(eventReport.settled_total)}</p>
        <p>مانده بدهی: {formatToman(eventReport.debt_total)}</p>
        <p>تسویه‌نشده: {eventReport.unsettled_count.toLocaleString("fa-IR")}</p>
      </div>
      <div className="table-scroll"><table><thead><tr><th>مهمان</th><th>کل هزینه</th>
        <th>تسویه‌شده</th><th>مانده</th><th>پیگیری</th></tr></thead><tbody>
        {eventReport.debtors.map((row) => <tr key={row.registration_id}>
          <td>{persianDigits(row.name)}</td><td>{formatToman(row.charges)}</td>
          <td>{formatToman(row.settled)}</td><td>{formatToman(row.debt)}</td>
          <td><Link className="text-link" href={`/panel/guests/${row.guest_id}`}>
            پروفایل و تسویه</Link></td>
        </tr>)}</tbody></table></div>
      {!eventReport.debtors.length && <p className="muted">بدهکاری برای این رویداد ثبت نشده است.</p>}
    </Card>}
    {!loading && <div className="report-table-card"><Card title="وضعیت مالی هشتی‌نشین‌ها">
      <p className="muted">بدهی خالص = بدهی رویدادها منهای موجودی کیف پول؛ جدول بر همین مبنا مرتب است.</p>
      <a className="button secondary" href={`/api/admin/reports/export/finance?${new URLSearchParams({
        q: applied.search, debtors_only: String(applied.debtorsOnly),
      })}`}>دریافت Excel جدول مالی</a>
      <div className="table-scroll report-table-scroll"><table className="report-table"><thead><tr><th>هشتی‌نشین</th><th>موجودی</th>
        <th>بدهی</th><th>خالص بدهی</th><th>رویداد تسویه‌نشده</th>
        <th>آخرین تراکنش</th></tr></thead><tbody>{finance?.items.map((row) =>
          <tr key={row.guest_id}><td><Link className="text-link"
            href={`/panel/guests/${row.guest_id}`}>{persianDigits(row.name)}</Link></td>
            <td>{formatToman(row.wallet_balance)}</td><td>{formatToman(row.debt)}</td>
            <td>{formatToman(row.net_debt)}</td><td>{row.unsettled_events.toLocaleString("fa-IR")}</td>
            <td>{row.last_transaction_at ? formatJalali(row.last_transaction_at) : "—"}</td></tr>)}</tbody></table></div>
      {!finance?.items.length && <p className="muted">موردی پیدا نشد.</p>}
    </Card></div>}
    {!loading && <div className="report-table-card"><Card title="گزارش هشتی‌نشین‌ها">
      <p className="muted">فیلترهای حضور و تاریخ روی سوابق رویداد اعمال می‌شوند؛ وضعیت مالی، خالص کل حساب است.</p>
      <a className="button secondary" href={`/api/admin/reports/export/guests?${applied.params}`}>
        دریافت Excel هشتی‌نشین‌ها</a>
      <div className="table-scroll report-table-scroll"><table className="report-table"><thead><tr><th>هشتی‌نشین</th><th>حضور</th><th>غیبت</th>
        <th>نوع</th><th>بدهی خالص</th></tr></thead><tbody>{guests?.items.map((row) =>
          <tr key={row.guest_id}><td><Link className="text-link"
            href={`/panel/guests/${row.guest_id}`}>{persianDigits(row.name)}</Link></td>
            <td>{row.attendance_count.toLocaleString("fa-IR")}</td>
            <td>{row.absence_count.toLocaleString("fa-IR")}</td>
            <td>{row.guest_kind === "new" ? "جدید" : "بازگشتی"}</td>
            <td>{formatToman(row.net_debt)}</td></tr>)}</tbody></table></div>
      {!guests?.items.length && <p className="muted">موردی با این فیلترها پیدا نشد.</p>}
      <div className="pagination"><span>{persianDigits(String(guests?.total ?? 0))} هشتی‌نشین</span>
        {offset > 0 && <Button type="button" className="secondary" onClick={() => {
          setLoading(true); setOffset(Math.max(0, offset - 50)); }}>قبلی</Button>}
        {guests && offset + 50 < guests.total && <Button type="button" className="secondary"
          onClick={() => { setLoading(true); setOffset(offset + 50); }}>بعدی</Button>}
      </div>
    </Card></div>}
    {!loading && charts && <div className="report-chart-grid">
      <Card title="دفعات حضور"><Bars rows={Object.entries(charts.attendance_buckets)
        .map(([label, count]) => ({ label: `${label} بار`, count }))} /></Card>
      <Card title="روند مشارکت"><Bars rows={charts.trend.map((row) =>
        ({ label: isoToJalali(row.date), count: row.count }))} /></Card>
      <Card title="جدید و بازگشتی"><Bars rows={[
        { label: "جدید", count: charts.new_vs_returning.new },
        { label: "بازگشتی", count: charts.new_vs_returning.returning },
      ]} /></Card>
      <Card title="نسبت حضور"><Bars rows={[
        { label: "حاضر", count: charts.attendance_ratio.present },
        { label: "غایب", count: charts.attendance_ratio.absent },
      ]} /></Card>
      <Card title="نوع غیبت"><Bars rows={[
        { label: "حفظ اعتبار", count: charts.absences.kept },
        { label: "سوخت اعتبار", count: charts.absences.forfeited },
      ]} /></Card>
      <Card title="رویدادهای پرمخاطب"><Bars rows={charts.popular_events.map((row) =>
        ({ label: row.title, count: row.count }))} /></Card>
      <Card title="علاقه‌مندی‌ها"><InterestDonut rows={charts.interests} /></Card>
    </div>}
    {session?.role === "super_admin" && reconciliation &&
      <Card title="تطبیق کیف پول با دفتر مالی">
        <p>این گزارش فقط‌خواندنی است و هیچ مغایرتی را خودکار اصلاح نمی‌کند.</p>
        <p>{reconciliation.mismatch_count_on_page.toLocaleString("fa-IR")} مغایرت در
          {" "}{reconciliation.items.length.toLocaleString("fa-IR")} کیف پول اول از
          {" "}{reconciliation.total.toLocaleString("fa-IR")} کیف پول</p>
        {reconciliation.items.filter((row) => !row.matches).map((row) =>
          <p key={row.wallet_id}><Link className="text-link"
            href={`/panel/guests/${row.guest_id}`}>{persianDigits(row.guest_name)}</Link> · مانده:
            {" "}{formatToman(row.cached_balance)} · دفتر: {formatToman(row.ledger_balance)} · اختلاف:
            {" "}{formatToman(row.difference)}</p>)}
      </Card>}
  </div></AppShell>;
}
