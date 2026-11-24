import Link from "next/link";
import { eventPlace, eventTime, type PublicEvent } from "@/lib/public-events";

export function PublicEventCard({ event }: { event: PublicEvent }) {
  return <article className="public-event-card">
    <Link href={`/events/${event.id}`} className="public-event-poster">
      {event.poster_url ? <img src={event.poster_url} alt={`پوستر ${event.title}`} />
        : <span className="public-event-placeholder">هشتی<span>.</span></span>}
    </Link>
    <div className="public-event-body">
      <span className="eyebrow">هشتی شمارهٔ {event.event_number}</span>
      <h3><Link href={`/events/${event.id}`}>{event.title}</Link></h3>
      <p>{eventTime(event)}</p>
      <p>{eventPlace(event)}</p>
      {event.hosts && <p>میزبان: {event.hosts}</p>}
      <span className="badge">ثبت‌نام {event.registration_status === "open" ? "باز" : "بسته"}</span>
    </div>
  </article>;
}
