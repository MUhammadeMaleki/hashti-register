import { notFound } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { EventEditor } from "@/components/events/event-editor";

export default async function EditEventPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const eventId = Number(id);
  if (!Number.isSafeInteger(eventId) || eventId < 1) notFound();
  return <AppShell kind="user"><EventEditor eventId={eventId} /></AppShell>;
}
