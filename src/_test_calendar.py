from calendar_sync import get_events_today_from_ics, find_free_slots_from_events, format_slot

events = get_events_today_from_ics()
print(f"Eventos hoy: {len(events)}")
for ev in events:
    print("-", ev["summary"])

slots = find_free_slots_from_events(events)
print("\nHuecos de estudio (>= min):")
for s in slots:
    print("  ", format_slot(s))
