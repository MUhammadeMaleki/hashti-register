"use client";

import Link from "next/link";
import { useState, type DragEvent, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui";
import { useSession } from "@/hooks/use-session";
import { errorMessage } from "@/lib/api";
import { eventImportApi, type EventImportPreview,
  type EventImportResult } from "@/lib/event-import";
import { formatJalali, formatToman } from "@/lib/format";
import styles from "./page.module.css";

export default function EventImportPage() {
  const { session, loading } = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<EventImportPreview | null>(null);
  const [result, setResult] = useState<EventImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  function selectFile(next: File | null) {
    setFile(next); setPreview(null); setResult(null); setError("");
  }

  function dropFile(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setDragging(false);
    if (busy) return;
    const next = event.dataTransfer.files[0];
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".xlsx")) {
      selectFile(null);
      setError("فقط فایل اکسل با پسوند XLSX پذیرفته می‌شود.");
      return;
    }
    selectFile(next);
  }

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
  const step = result ? 3 : preview ? 2 : 1;
  return <AppShell kind="user"><div className={styles.page}>
    <section className={styles.hero} aria-labelledby="event-import-title">
      <div><span className={styles.eyebrow}>هشتی‌ها / ورود آرشیو</span>
        <h2 id="event-import-title">هشتی‌های گذشته را یک‌جا وارد کنید</h2>
        <p>فایل اکسل را آماده کنید، ردیف‌ها را پیش از ورود ببینید و سپس تأیید کنید.</p></div>
      <Link className={styles.backLink} href="/panel/events">↗ بازگشت به هشتی‌ها</Link>
    </section>

    <ol className={styles.steps} aria-label="مراحل ورود آرشیو">
      <li className={step >= 1 ? styles.stepActive : ""}><span>۱</span><div><strong>آماده‌سازی</strong><small>فایل نمونه و اطلاعات</small></div></li>
      <li className={step >= 2 ? styles.stepActive : ""}><span>۲</span><div><strong>پیش‌نمایش</strong><small>بررسی ردیف‌ها</small></div></li>
      <li className={step >= 3 ? styles.stepActive : ""}><span>۳</span><div><strong>ورود به آرشیو</strong><small>نتیجهٔ نهایی</small></div></li>
    </ol>

    {loading ? <p className={styles.loadingState}>در حال بررسی دسترسی…</p> :
      session?.role !== "super_admin" ? <p className="alert error">ورود آرشیو فقط برای مدیر هشتی مجاز است.</p> : <>
      {error && <p className="alert error" role="alert">{error}</p>}
      <div className={styles.intakeGrid}>
        <section className={styles.uploadPanel} aria-labelledby="upload-title">
          <header className={styles.panelHeading}><span className={styles.panelIndex}>۰۱ / انتخاب فایل</span>
            <h3 id="upload-title">فایل آرشیو را اینجا بگذارید</h3>
            <p>فایل ابتدا فقط بررسی می‌شود؛ تا وقتی تأیید نکنید، هشتی‌ای وارد نخواهد شد.</p></header>
          <form onSubmit={inspect} className={styles.uploadForm}>
            <div className={`${styles.dropZone} ${dragging ? styles.dragging : ""}`}
              onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }}
              onDragLeave={() => setDragging(false)} onDrop={dropFile}>
              <input id="event-import-file" className="sr-only" type="file" accept=".xlsx"
                disabled={busy} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} />
              <label htmlFor="event-import-file"><span className={styles.uploadIcon} aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none"><path d="M16 21V5m0 0-6 6m6-6 6 6M5 20v5a3 3 0 0 0 3 3h16a3 3 0 0 0 3-3v-5" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </span><strong>{file ? "فایل انتخاب شد" : "فایل اکسل را انتخاب کنید"}</strong>
                <span>{file ? file.name : "برای انتخاب بزنید یا فایل را اینجا رها کنید"}</span>
                <small>XLSX · حداکثر ۳ مگابایت · تا ۵۰۰۰ ردیف</small></label>
            </div>
            {file && <div className={styles.selectedFile} aria-live="polite">
              <span className={styles.fileType}>XLSX</span><span className={styles.fileName}>{file.name}</span>
              <small>{Math.ceil(file.size / 1024).toLocaleString("fa-IR")} کیلوبایت</small>
            </div>}
            <Button type="submit" className={`primary ${styles.inspectButton}`} disabled={!file || busy}>
              {busy && !preview ? "در حال بررسی…" : "بررسی و پیش‌نمایش فایل"}<span aria-hidden="true">←</span>
            </Button>
          </form>
        </section>
        <aside className={styles.guidePanel} aria-labelledby="guide-title">
          <div className={styles.guideTop}><span className={styles.panelIndex}>راهنمای سریع</span>
            <h3 id="guide-title">از فایل نمونه شروع کنید</h3>
            <p>ستون‌ها از قبل آماده‌اند؛ اطلاعات هشتی‌های قدیمی را در همان قالب وارد کنید.</p>
            <a className={styles.templateLink} href="/api/admin/import/events/template">↓ دریافت فایل نمونه</a></div>
          <ul className={styles.tips}>
            <li><span>۱</span><p><strong>شمارهٔ هشتی الزامی است.</strong> اگر عنوان خالی باشد، عنوان هشتی با همان شماره ساخته می‌شود.</p></li>
            <li><span>۲</span><p><strong>تاریخ و ساعت</strong> را با تاریخ اکسل یا قالب میلادی YYYY-MM-DD و ساعت HH:MM بنویسید.</p></li>
            <li><span>۳</span><p><strong>ستون‌های دیگر اختیاری‌اند.</strong> پیش‌نمایش، ردیف‌های ناسازگار را نشان می‌دهد.</p></li>
          </ul>
        </aside>
      </div>

      {preview && <section className={styles.reviewPanel} aria-labelledby="preview-title">
        <header className={styles.panelHeading}><span className={styles.panelIndex}>۰۲ / بررسی پیش از ورود</span>
          <h3 id="preview-title">پیش‌نمایش فایل</h3>
          <p>تا ۱۰۰ ردیف معتبر نخست نمایش داده می‌شود؛ تأیید، همهٔ ردیف‌های معتبر را وارد می‌کند.</p></header>
        <div className={styles.summary} aria-live="polite">
          <div><small>ردیف بررسی‌شده</small><strong>{preview.total.toLocaleString("fa-IR")}</strong></div>
          <div className={styles.valid}><small>آمادهٔ ورود</small><strong>{preview.valid_count.toLocaleString("fa-IR")}</strong></div>
          <div className={styles.invalid}><small>دارای خطا</small><strong>{preview.error_count.toLocaleString("fa-IR")}</strong></div>
        </div>
        {!!preview.preview_rows.length && <div className={styles.tableScroll}><table className={styles.table}>
          <thead><tr><th>ردیف</th><th>شماره</th><th>عنوان هشتی</th><th>تاریخ</th><th>کافه</th><th>ورودی</th><th>ثبت‌نام</th></tr></thead>
          <tbody>{preview.preview_rows.map((row) => <tr key={row.row}>
            <td>{row.row.toLocaleString("fa-IR")}</td>
            <td><span className={styles.number}>{row.event_number.toLocaleString("fa-IR")}</span></td>
            <td className={styles.titleCell}>{row.title}</td>
            <td>{row.event_date ? formatJalali(`${row.event_date}T12:00:00`) : "—"}</td>
            <td>{row.location_name ?? row.location_address ?? "—"}</td>
            <td>{formatToman(row.entry_fee)}</td>
            <td>{row.registration_status === "open" ? "باز" : "بسته"}</td>
          </tr>)}</tbody></table></div>}
        <div className={styles.reviewFooter}><p>فقط ردیف‌های معتبر وارد آرشیو می‌شوند.</p>
          <Button type="button" className={`primary ${styles.confirmButton}`}
            disabled={busy || !preview.valid_count} onClick={confirm}>
            {busy ? "در حال ورود…" : "تأیید ورود ردیف‌های معتبر"}</Button></div>
      </section>}

      {result && <section className={styles.resultPanel} aria-live="polite" aria-labelledby="result-title">
        <span className={styles.resultMark} aria-hidden="true">✓</span>
        <div><span className={styles.panelIndex}>۰۳ / نتیجهٔ ورود</span><h3 id="result-title">ورود آرشیو انجام شد</h3>
          <p>از {result.total.toLocaleString("fa-IR")} ردیف، <strong>{result.imported_count.toLocaleString("fa-IR")} هشتی</strong> وارد شد و {result.error_count.toLocaleString("fa-IR")} ردیف وارد نشد.</p></div>
        <Link className={styles.resultLink} href="/panel/events">دیدن هشتی‌ها <span aria-hidden="true">←</span></Link>
      </section>}

      {!!errors.length && <section className={styles.errorsPanel} aria-labelledby="errors-title">
        <header className={styles.panelHeading}><span className={styles.panelIndex}>ردیف‌های نیازمند اصلاح</span>
          <h3 id="errors-title">خطاهای فایل</h3>
          <p>این ردیف‌ها وارد نشده‌اند. فایل را اصلاح کنید و دوباره برای بررسی بفرستید.</p></header>
        <div className={styles.tableScroll}><table className={styles.table}>
          <thead><tr><th>ردیف اکسل</th><th>دلیل</th></tr></thead>
          <tbody>{errors.map((item) => <tr key={item.row}>
            <td><span className={styles.errorNumber}>{item.row.toLocaleString("fa-IR")}</span></td>
            <td>{item.reason}</td></tr>)}</tbody>
        </table></div>
      </section>}
    </>}
  </div></AppShell>;
}
