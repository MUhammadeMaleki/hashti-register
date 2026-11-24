"use client";

import { useRef, useState } from "react";
import { PublicEventCard } from "@/components/public-event-card";
import type { PublicEvent } from "@/lib/public-events";

export function OpenEventsSlider({ events }: { events: PublicEvent[] }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  function goTo(next: number) {
    const target = Math.max(0, Math.min(events.length - 1, next));
    trackRef.current?.children[target]?.scrollIntoView({
      behavior: "smooth", inline: "start", block: "nearest",
    });
    setIndex(target);
  }

  function syncIndex() {
    const track = trackRef.current;
    if (!track) return;
    const right = track.getBoundingClientRect().right;
    let closest = 0;
    let distance = Infinity;
    Array.from(track.children).forEach((child, position) => {
      const current = Math.abs(child.getBoundingClientRect().right - right);
      if (current < distance) { distance = current; closest = position; }
    });
    setIndex(closest);
  }

  return <div className="open-events-slider">
    <div className="slider-track" ref={trackRef} onScroll={syncIndex}
      aria-label="هشتی‌های باز">
      {events.map((event) => <PublicEventCard key={event.id} event={event} />)}
    </div>
    {events.length > 1 && <div className="slider-controls">
      <span aria-live="polite">{new Intl.NumberFormat("fa-IR").format(index + 1)} از {new Intl.NumberFormat("fa-IR").format(events.length)}</span>
      <div className="slider-arrows">
        <button type="button" onClick={() => goTo(index - 1)} disabled={index === 0}
          aria-label="رویداد قبلی">→</button>
        <button type="button" onClick={() => goTo(index + 1)} disabled={index === events.length - 1}
          aria-label="رویداد بعدی">←</button>
      </div>
    </div>}
  </div>;
}
