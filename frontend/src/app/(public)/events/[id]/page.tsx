import Link from "next/link";
import { notFound } from "next/navigation";
import { PublicRegistrationForm } from "@/components/public-registration-form";
import { eventFee, eventPlace, eventTime, publicEvents, safeExternalUrl } from "@/lib/public-events";

export default async function EventDetails({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const eventId = Number(id);
  if (!Number.isSafeInteger(eventId) || eventId < 1) notFound();
  const [event, settings] = await Promise.all([
    publicEvents.get(eventId), publicEvents.settings(),
  ]);
  if (!event) notFound();
  const mapLink = safeExternalUrl(event.location?.map_link ?? null);
  const telegram = safeExternalUrl(settings?.telegram_support_link ?? null);
  const bale = safeExternalUrl(settings?.bale_support_link ?? null);
  const registrationOpen = event.registration_status === "open";

  return <>
    <article className="event-detail">
      <section className="event-detail-hero" aria-labelledby="event-title">
        <div className="event-detail-intro">
          <Link href="/" className="event-detail-back">همهٔ هشتی‌ها <span aria-hidden="true">←</span></Link>
          <div className="event-detail-labels">
            <span className="event-detail-number">هشتی شمارهٔ {new Intl.NumberFormat("fa-IR").format(event.event_number)}</span>
            <span className={`event-detail-status${registrationOpen ? " is-open" : ""}`}>
              {registrationOpen ? "ثبت‌نام باز است" : "ثبت‌نام بسته است"}
            </span>
          </div>
          <h1 id="event-title">{event.title}</h1>
          {event.description && <p className="event-detail-lead">{event.description}</p>}
          <div className="event-detail-highlights">
            <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 15h3" /></svg><div><span>زمان هشتی</span><strong>{eventTime(event)}</strong></div></div>
            <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg><div><span>جای هشتی</span><strong>{eventPlace(event)}</strong></div></div>
            <div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M8 10h8M8 14h8" /></svg><div><span>هزینهٔ ورود</span><strong>{eventFee(event)}</strong></div></div>
          </div>
          {registrationOpen && <a className="event-detail-cta" href="#registration">
            صندلی‌ات را رزرو کن <span aria-hidden="true">←</span>
          </a>}
        </div>
        <div className="event-detail-art">
          <div className="event-detail-poster">{event.poster_url
            ? <img src={event.poster_url} alt={`پوستر ${event.title}`} />
            : <span className="public-event-placeholder">هشتی<span>.</span></span>}</div>
        </div>
      </section>

      {event.public_note && <aside className="event-detail-note" aria-labelledby="event-note-title">
        <div className="event-detail-note-heading">
          <span className="event-detail-note-mark" aria-hidden="true">✳</span>
          <h2 id="event-note-title">یادداشت هشتی</h2>
        </div>
        <p>{event.public_note}</p>
      </aside>}

      <div className="event-detail-main">
        <div className="event-detail-about">
          <section className="event-detail-panel" aria-labelledby="event-about-title">
            <p className="event-detail-kicker">پیش از اینکه دور هم بنشینیم</p>
            <h2 id="event-about-title">دربارهٔ این هشتی</h2>
            {event.description ? <p className="event-detail-description">{event.description}</p>
              : <p className="event-detail-description">جزئیات این هشتی به‌زودی اعلام می‌شود.</p>}
            <dl className="event-detail-facts">
              <div><dt>زمان</dt><dd>{eventTime(event)}</dd></div>
              <div><dt>مکان</dt><dd>{eventPlace(event)}
                {event.location?.address && <> · {event.location.address}</>}
                {mapLink && <> · <a className="text-link" href={mapLink} target="_blank"
                  rel="noopener noreferrer">نمایش روی نقشه</a></>}</dd></div>
              {event.hosts && <div><dt>میزبان</dt><dd>{event.hosts}</dd></div>}
              <div><dt>هزینهٔ ورود</dt><dd>{eventFee(event)}</dd></div>
            </dl>
          </section>
        </div>
        <div className="event-detail-aside">
          <PublicRegistrationForm eventId={event.id} registrationOpen={registrationOpen}
            cardNumber={settings?.card_number ?? null} accountHolder={settings?.account_holder ?? null} />
          {(telegram || bale || settings?.support_phone) && <section className="public-support">
            <h2>ارتباط با پشتیبانی</h2>
            {telegram && <a className="text-link" href={telegram} target="_blank"
              rel="noopener noreferrer">تلگرام</a>}
            {bale && <a className="text-link" href={bale} target="_blank"
              rel="noopener noreferrer">بله</a>}
            {settings?.support_phone && <a className="text-link"
              href={`tel:${settings.support_phone.replace(/[^+\d]/g, "")}`}>
              {settings.support_phone}</a>}
          </section>}
        </div>
      </div>
    </article>
  </>;
}
