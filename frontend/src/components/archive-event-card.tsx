import Link from "next/link";
import { persianDigits } from "@/lib/format";
import { eventPlace, eventTime, type PublicEvent } from "@/lib/public-events";

export function ArchiveEventCard({ event }: { event: PublicEvent }) {
  const href = `/events/${event.id}`;
  return <article className="archive-event-card">
    <div className="archive-event-top">
      <Link href={href} className="archive-event-cover" aria-label={`جزئیات ${event.title}`}>
        {event.poster_url ? <img src={event.poster_url} alt={`پوستر ${event.title}`} loading="lazy" />
          : <span className="archive-event-placeholder" aria-hidden="true">هشتی<span>.</span></span>}
        <span className="archive-event-stamp">آرشیو</span>
      </Link>
      <div className="archive-event-info">
        <span className="archive-event-number">هشتی شمارهٔ {persianDigits(String(event.event_number))}</span>
        <h3><Link href={href}>{event.title}</Link></h3>
        {event.hosts && <p className="archive-event-hosts">با میزبانی {persianDigits(event.hosts)}</p>}
      </div>
    </div>
    <div className="archive-event-details">
      <p className="archive-event-meta"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18" /></svg><span><small>زمان</small><strong>{persianDigits(eventTime(event))}</strong></span></p>
      <p className="archive-event-meta"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg><span><small>مکان</small><strong>{persianDigits(eventPlace(event))}</strong></span></p>
    </div>
    <Link href={href} className="archive-event-link">مرور این هشتی <span aria-hidden="true">←</span></Link>
  </article>;
}
