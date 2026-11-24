"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, Card } from "@/components/ui";
import { useSession } from "@/hooks/use-session";
import { errorMessage } from "@/lib/api";
import { eventImportApi, type EventImportPreview,
  type EventImportResult } from "@/lib/event-import";
import { formatJalali, formatToman } from "@/lib/format";

export default function EventImportPage() {
  const { session } = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<EventImportPreview | null>(null);
  const [result, setResult] = useState<EventImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function inspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true); setError(""); setPreview(null); setResult(null);
    try { setPreview(await eventImportApi.preview(file)); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function confirm() {
    if (!file || !preview || busy) return;
    setBusy(true); setError("");
    try { setResult(await eventImportApi.confirm(file, preview.preview_token)); setPreview(null); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  const errors = result?.errors ?? preview?.errors ?? [];
  return <AppShell kind="user"><div className="editor-stack">
    <div className="section-heading"><div><h2>ورود آرشیو رویدادها</h2>
      <p className="muted">رویدادهای قدیمی در همان بانک رویدادها ذخیره می‌شوند.</p></div>
      <Link className="button secondary" href="/panel/events">بازگشت به رویدادها</Link>
    </div>
    {session?.role !== "super_admin" ? <p className="alert error">ورود آرشیو فقط برای مدیر هشتی مجاز است.</p> : <>
      {error && <p className="alert error" role="alert">{error}</p>}
      <Card title="فایل Excel"><p>شماره رویداد الزامی است؛ عنوان خالی به «هشتی شماره» تبدیل می‌شود.
        تاریخ را به‌صورت تاریخ Excel یا YYYY-MM-DD میلادی و ساعت را HH:MM وارد کنید.
        دیگر ستون‌ها می‌توانند خالی باشند. حداکثر ۵۰۰۰ ردیف و ۳ مگابایت.</p>
        <a className="button secondary" href="/api/admin/import/events/template">دریافت فایل نمونه</a>
        <form className="form-stack" onSubmit={inspect}>
          <div className="field"><label htmlFor="event-import-file">فایل XLSX</label>
            <input id="event-import-file" type="file" accept=".xlsx" required
              onChange={(event) => { setFile(event.target.files?.[0] ?? null);
                setPreview(null); setResult(null); setError(""); }} /></div>
          <Button type="submit" className="primary" disabled={!file || busy}>
            {busy ? "در حال بررسی…" : "بررسی و پیش‌نمایش"}</Button>
        </form>
      </Card>
      {preview && <Card title="پیش‌نمایش پیش از ورود">
        <p>{preview.total.toLocaleString("fa-IR")} ردیف بررسی شد؛
          {" "}{preview.valid_count.toLocaleString("fa-IR")} معتبر و
          {" "}{preview.error_count.toLocaleString("fa-IR")} دارای خطا.</p>
        <p className="muted">حداکثر ۱۰۰ ردیف معتبر اول نمایش داده می‌شود. تأیید، همهٔ ردیف‌های معتبر را وارد می‌کند.</p>
        <div className="table-scroll"><table><thead><tr><th>ردیف</th><th>شماره</th>
          <th>عنوان</th><th>تاریخ</th><th>مکان</th><th>ورودی</th><th>ثبت‌نام</th>
          </tr></thead><tbody>{preview.preview_rows.map((row) => <tr key={row.row}>
            <td>{row.row}</td><td>{row.event_number}</td><td>{row.title}</td>
            <td>{row.event_date ? formatJalali(`${row.event_date}T12:00:00`) : "—"}</td>
            <td>{row.location_name ?? row.location_address ?? "—"}</td>
            <td>{formatToman(row.entry_fee)}</td>
            <td>{row.registration_status === "open" ? "باز" : "بسته"}</td>
          </tr>)}</tbody></table></div>
        <Button type="button" className="primary" disabled={busy || !preview.valid_count}
          onClick={confirm}>{busy ? "در حال ورود…" : "تأیید ورود ردیف‌های معتبر"}</Button>
      </Card>}
      {result && <Card title="نتیجه ورود"><p>از {result.total.toLocaleString("fa-IR")} ردیف،
        {" "}{result.imported_count.toLocaleString("fa-IR")} رویداد وارد شد و
        {" "}{result.error_count.toLocaleString("fa-IR")} ردیف وارد نشد.</p></Card>}
      {!!errors.length && <Card title="خطاهای ردیفی"><div className="table-scroll">
        <table><thead><tr><th>ردیف Excel</th><th>دلیل</th></tr></thead><tbody>
          {errors.map((item) => <tr key={item.row}><td>{item.row}</td><td>{item.reason}</td></tr>)}
        </tbody></table></div></Card>}
    </>}
  </div></AppShell>;
}
