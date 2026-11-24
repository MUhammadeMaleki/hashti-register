"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { eventsApi, type Location, type Page } from "@/lib/events";

export function LocationManager() {
  const [page, setPage] = useState<Page<Location> | null>(null);
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [address, setAddress] = useState("");
  const [mapLink, setMapLink] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setPage(await eventsApi.locations(offset)); setError(""); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setLoading(false); }
  }, [offset]);
  useEffect(() => { void load(); }, [load]);

  function edit(location: Location) {
    setEditing(location.id); setTitle(location.title); setAddress(location.address);
    setMapLink(location.map_link ?? ""); setError(""); setNotice("");
  }
  function reset() {
    setEditing(null); setTitle(""); setAddress(""); setMapLink("");
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const body = { title: title.trim(), address: address.trim(), map_link: mapLink.trim() || null };
      if (editing) await eventsApi.updateLocation(editing, body);
      else await eventsApi.createLocation(body);
      reset(); setNotice("کافه ذخیره شد."); await load();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  async function remove(location: Location) {
    if (busy || !window.confirm(`کافهٔ «${location.title}» حذف شود؟`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await eventsApi.removeLocation(location.id);
      setNotice("کافه حذف شد.");
      if (page?.items.length === 1 && offset > 0) setOffset(offset - 50);
      else await load();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="cafes-page">
    <header className="cafes-intro"><div><span>قرارهای هشتی</span><h2>کافه‌ها و جاهای دورهمی</h2>
      <p>کافه‌های هشتی را اینجا ثبت و مدیریت کنید؛ تغییر نشانی در همهٔ هشتی‌های متصل دیده می‌شود.</p></div>
      <span className="cafes-intro-count">{page ? page.total.toLocaleString("fa-IR") : "—"}<small>کافهٔ ثبت‌شده</small></span>
    </header>
    {error && <p role="alert" className="alert error">{error}</p>}
    {notice && <p role="status" className="alert success">{notice}</p>}
    <div className="cafes-layout">
      <section className="cafes-form-panel" id="cafe-form" aria-labelledby="cafe-form-title">
        <span className="cafes-panel-kicker">{editing ? "ویرایش اطلاعات" : "ثبت فضای تازه"}</span>
        <h3 id="cafe-form-title">{editing ? "ویرایش کافه" : "کافهٔ جدید"}</h3>
        <p>نام و نشانی را یک‌بار ثبت کنید تا هنگام ساخت هشتی در دسترس باشد.</p>
        <form onSubmit={save} className="form-stack">
          <Field id="location-title" label="نام کافه" value={title}
            onChange={(event) => setTitle(event.target.value)} maxLength={200} required />
          <div className="field"><label htmlFor="location-address">نشانی</label><textarea
            id="location-address" rows={3} value={address}
            onChange={(event) => setAddress(event.target.value)} required /></div>
          <Field id="map-link" label="لینک نقشه (اختیاری)" type="url" dir="ltr"
            value={mapLink} onChange={(event) => setMapLink(event.target.value)} />
          <div className="cafes-form-actions"><Button type="submit" className="primary" disabled={busy}>
            {busy ? "در حال ذخیره…" : editing ? "ذخیره تغییرات" : "افزودن کافه"}</Button>
            {editing && <Button type="button" className="secondary" onClick={reset}>انصراف</Button>}</div>
        </form>
      </section>
      <section className="cafes-directory" aria-labelledby="cafes-list-title">
        <div className="cafes-directory-heading"><div><span className="cafes-panel-kicker">فهرست فضاها</span>
          <h3 id="cafes-list-title">کافه‌های ثبت‌شده</h3></div>
          <span>{page ? `${page.total.toLocaleString("fa-IR")} مورد` : "—"}</span>
        </div>
        {loading ? <p className="cafes-empty" role="status">در حال دریافت کافه‌ها…</p> :
          page?.items.length ? <div className="cafes-list">
            {page.items.map((location) => <article className="cafe-item" key={location.id}>
              <div className="cafe-item-mark" aria-hidden="true">ک</div>
              <div className="cafe-item-content"><h4>{location.title}</h4>
                <p>{location.address}</p>
                <span>{location.linked_event_count.toLocaleString("fa-IR")} هشتیِ متصل</span></div>
              <div className="cafe-item-actions">
                <Button type="button" className="secondary" onClick={() => edit(location)}>ویرایش</Button>
                <Button type="button" className="danger-button" disabled={location.linked_event_count > 0}
                  title={location.linked_event_count > 0 ? "کافهٔ متصل به هشتی را نمی‌توان حذف کرد" : undefined}
                  onClick={() => remove(location)}>حذف</Button>
              </div>
            </article>)}
          </div> : <p className="cafes-empty">هنوز کافه‌ای ثبت نشده است.</p>}
        {!loading && page && page.total > 50 && <nav className="cafes-pagination" aria-label="صفحات کافه‌ها">
          <Button type="button" className="secondary" disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 50))}>قبلی</Button>
          <span>صفحهٔ {(Math.floor(offset / 50) + 1).toLocaleString("fa-IR")} از {Math.ceil(page.total / 50).toLocaleString("fa-IR")}</span>
          <Button type="button" className="secondary" disabled={offset + 50 >= page.total}
            onClick={() => setOffset(offset + 50)}>بعدی</Button>
        </nav>}
      </section>
    </div>
  </div>;
}
