import { AppShell } from "@/components/app-shell";
import { EventList } from "@/components/events/event-list";

export default function EventsPage() {
  return <AppShell kind="user"><EventList /></AppShell>;
}
