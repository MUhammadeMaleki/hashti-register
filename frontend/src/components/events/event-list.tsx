"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useSession } from "@/hooks/use-session";
import { errorMessage } from "@/lib/api";
import { eventsApi, type EventListFilters, type EventRecord, type Page } from "@/lib/events";
import { formatJalali, formatToman, persianDigits } from "@/lib/format";

function eventTime(event: EventRecord): string {
  if (event.time_mode === "approximate") return event.time_text || "زمان تقریبی";
  if (event.time_mode === "tba") return "اعلام بعدی";
  const date = event.event_date ? formatJalali(`${event.event_date}T12:00:00`) : "اعلام بعدی";
  return event.start_time ? `${date} · ساعت ${persianDigits(event.start_time.slice(0, 5))}` : date;
}

function eventPlace(event: EventRecord): string {
  if (event.location_mode === "tba") return "اعلام بعدی";
  return event.location?.title ?? event.location_text ?? "اعلام بعدی";
}

export function EventList() {
  const { session } = useSession();
  const [offset, setOffset] = useState(0);
  const [period, setPeriod] = useState<NonNullable<EventListFilters["period"]>>("all");
  const [registrationStatus, setRegistrationStatus] = useState<NonNullable<EventListFilters["registrationStatus"]>>("all");
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [page, setPage] = useState<Page<EventRecord> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => { setOffset(0); setSubmittedSearch(search.trim()); }, 350);
    return () => window.clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    eventsApi.list(offset, 20, { period, registrationStatus, search: submittedSearch })
      .then((value) => { if (active) { setPage(value); setError(""); } })
      .catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [offset, period, registrationStatus, submittedSearch]);
  const pageNumber = Math.floor(offset / 20) + 1;
  const pageCount = Math.max(1, Math.ceil((page?.total ?? 0) / 20));

  return <div className="panel-events">
    <section className="panel-events-hero" aria-labelledby="panel-events-title">
      <div className="panel-events-hero-copy">
        <span className="panel-events-kicker">دفتر هشتی‌ها</span>
        <h2 id="panel-events-title">هر هشتی، یک گفت‌وگوی تازه.</h2>
        <p>هشتی‌های پیش‌رو، برگزارشده و لغوشده را از همین‌جا مدیریت کنید.</p>
      </div>
      <div className="panel-events-hero-actions">
        {session?.role === "super_admin" &&
          <Link className="panel-events-import" href="/panel/events/import">ورود آرشیو اکسل</Link>}
        <Link className="panel-events-create" href="/panel/events/new"><span aria-hidden="true">＋</span> ساخت هشتی</Link>
      </div>
    </section>

    <section className="panel-events-list" aria-label="فهرست هشتی‌ها">
      <div className="panel-events-list-heading"><div><span>فهرست هشتی‌ها</span>
        <h3>همهٔ هشتی‌ها</h3></div>
        <span className="panel-events-total">{page ? `${page.total.toLocaleString("fa-IR")} هشتی` : "—"}</span>
      </div>
      <div className="panel-events-filters">
        <div className="panel-events-periods" role="group" aria-label="دورهٔ هشتی‌ها">
          {([["all", "همه"], ["upcoming", "پیش‌رو"], ["archive", "گذشته"], ["cancelled", "لغوشده"]] as const).map(([value, label]) =>
            <button type="button" key={value} className={period === value ? "is-active" : ""}
              aria-pressed={period === value} onClick={() => { setOffset(0); setPeriod(value); }}>{label}</button>)}
        </div>
        <div className="panel-events-filter-fields">
          <label className="panel-events-search"><span className="sr-only">جست‌وجوی هشتی</span>
            <input type="search" value={search} maxLength={100} placeholder="جست‌وجوی عنوان، شماره یا میزبان…"
              onChange={(event) => setSearch(event.target.value)} /></label>
          <label className="panel-events-registration-filter"><span className="sr-only">وضعیت ثبت‌نام</span>
            <select value={registrationStatus} onChange={(event) => {
              setOffset(0); setRegistrationStatus(event.target.value as NonNullable<EventListFilters["registrationStatus"]>);
            }}>
              <option value="all">همهٔ ثبت‌نام‌ها</option>
              <option value="open">ثبت‌نام باز</option>
              <option value="closed">ثبت‌نام بسته</option>
            </select></label>
        </div>
      </div>
      {loading ? <p className="panel-events-state" role="status">در حال دریافت هشتی‌ها…</p> :
        error ? <p role="alert" className="alert error">{error}</p> :
          page?.items.length ? <div className="panel-events-rows">
            {page.items.map((event) => <article className="panel-event-row" key={event.id}>
              <div className={`panel-event-poster${event.poster_url ? "" : " is-empty"}`}>
                <img src={event.poster_url || "/hashti-mark.svg"} alt="" loading="lazy" />
              </div>
              <div className="panel-event-heading"><span>هشتی شمارهٔ {event.event_number.toLocaleString("fa-IR")}</span>
                <h4><Link href={`/panel/events/${event.id}`}>{event.title}</Link></h4>
                <span className={`panel-event-status ${event.is_cancelled ? "is-cancelled" :
                  event.registration_status === "open" ? "is-open" : "is-closed"}`}>
                  {event.is_cancelled ? "لغوشده" : event.registration_status === "open" ? "ثبت‌نام باز" : "ثبت‌نام بسته"}
                </span></div>
              <dl className="panel-event-facts">
                <div><dt>زمان</dt><dd>{eventTime(event)}</dd></div>
                <div><dt>مکان</dt><dd>{eventPlace(event)}</dd></div>
                <div><dt>ورودی</dt><dd>{event.entry_fee === 0 ? "رایگان" : formatToman(event.entry_fee)}</dd></div>
              </dl>
              <Link className="panel-event-open" href={`/panel/events/${event.id}`} aria-label={`مدیریت ${event.title}`}>
                <span>مدیریت</span><span aria-hidden="true">←</span>
              </Link>
            </article>)}
          </div> : <p className="panel-events-state">هشتی‌ای با این جست‌وجو و فیلترها پیدا نشد.</p>}
      {!loading && !error && page && pageCount > 1 && <nav className="panel-events-pagination" aria-label="صفحات هشتی‌ها">
        <Button className="secondary" type="button" disabled={offset === 0}
          onClick={() => { setLoading(true); setOffset(Math.max(0, offset - 20)); }}>صفحهٔ قبل</Button>
        <span>صفحهٔ {pageNumber.toLocaleString("fa-IR")} از {pageCount.toLocaleString("fa-IR")}</span>
        <Button className="secondary" type="button" disabled={offset + 20 >= page.total}
          onClick={() => { setLoading(true); setOffset(offset + 20); }}>صفحهٔ بعد</Button>
      </nav>}
    </section>
  </div>;
}
