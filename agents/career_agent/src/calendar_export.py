from datetime import date, datetime
from pathlib import Path
from db import load_tracker

OUT = Path(__file__).resolve().parent.parent / "data" / "career_calendar.ics"

def ics_event(uid, day, summary):
    """One all-day calendar event in iCalendar format."""
    d = day if isinstance(day, date) else datetime.strptime(str(day), "%Y-%m-%d").date()
    return ("BEGIN:VEVENT\r\n"
            f"UID:{uid}@cognipath\r\n"
            f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}\r\n"
            f"DTSTART;VALUE=DATE:{d:%Y%m%d}\r\n"
            f"SUMMARY:{summary}\r\n"
            # Reminder one day before
            "BEGIN:VALARM\r\nTRIGGER:-P1D\r\nACTION:DISPLAY\r\n"
            f"DESCRIPTION:{summary}\r\nEND:VALARM\r\n"
            "END:VEVENT\r\n")

def export_calendar(user_id):
    """Write deadlines and interview dates from the tracker to an .ics file."""
    events = []
    for r in load_tracker(user_id):
        name = f"{r['title']} @ {r['company']}"
        if r["deadline"] and r["status"] == "planned":
            events.append(ics_event(f"deadline-{r['application_id']}", r["deadline"], f"Apply deadline: {name}"))
        if r["interview_date"]:
            events.append(ics_event(f"interview-{r['application_id']}", r["interview_date"], f"Interview: {name}"))
    OUT.write_text("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//CogniPath//Career Agent//EN\r\n"
                   + "".join(events) + "END:VCALENDAR\r\n", encoding="utf-8")
    print(f"Saved {len(events)} events to {OUT}")

if __name__ == "__main__":
        # Ask which user to export
    user_id = input("User ID: ").strip()
    export_calendar(user_id)