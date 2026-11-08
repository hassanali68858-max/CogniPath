from datetime import date
from db import load_tracker, update_application, load_recommendations, save_feedback, add_application
def show_tracker(user_id):
    """Print the user's applications as a simple table."""
    rows = load_tracker(user_id)
    if not rows:
        print("No applications yet.")
        return
    print(f"{'ID':<4}{'Job':<28}{'Company':<18}{'Match':<7}{'Deadline':<12}"
          f"{'Status':<12}{'Invited':<9}{'Accepted':<10}{'Interview'}")
    for r in rows:
        match = f"{round(r['match'] * 100)}%" if r["match"] is not None else "-"
        print(f"{r['application_id']:<4}{r['title'][:26]:<28}{r['company'][:16]:<18}"
              f"{match:<7}{str(r['deadline'] or '-'):<12}{r['status']:<12}"
              f"{'Yes' if r['interview_invited'] else 'No':<9}{r['accepted']:<10}"
              f"{r['interview_date'] or '-'}")
        
def show_recommendations(user_id, top=10):
    """Print the best matching jobs for the user."""
    rows = load_recommendations(user_id)[:top]
    if not rows:
        print("No recommendations yet.")
        return
    print("\nRecommended jobs (★ = liked, shown first):")
    print(f"{'ID':<5}{'Match':<7}{'Boost':<8}{'Job':<40}{'Company':<18}")
    for r in rows:
        match = f"{round(r['base'] * 100)}%"
        # Extra points from your likes/dislikes
        boost = f"{round((r['score'] - r['base']) * 100):+d}%"
        star = "★ " if r["liked"] else ""
        company = (r['company'] or '-')[:16]
        print(f"{r['job_posting_id']:<5}{match:<7}{boost:<8}{(star + r['title'])[:38]:<40}{company:<18}")

def ask_feedback(user_id):
    """Ask the user to like or dislike recommended jobs."""
    while True:
        job_id = input("\nJob ID to rate (Enter = skip): ").strip()
        if not job_id:
            return
        # Job IDs are numbers, e.g. 59
        if not job_id.isdigit():
            print("Please type a job ID number from the list.")
            continue
        vote = input("Like? (y/n): ").strip().lower()
        if vote not in ("y", "n"):
            print("Please type y or n.")
            continue
        reason = input("Reason (optional): ").strip() or None
        save_feedback(user_id, int(job_id), vote == "y", reason)
        print("Feedback saved.")

def ask_add(user_id):
    """Let the user move recommended jobs into the tracker."""
    while True:
        job_id = input("\nJob ID to add to tracker (Enter = skip): ").strip()
        if not job_id:
            return
        if not job_id.isdigit():
            print("Please type a number.")
            continue
        applied = input("Already applied? (y/n): ").strip().lower() == "y"
        app_id = add_application(user_id, int(job_id))
        if applied:
            update_application(app_id, status="applied", applied_at=date.today())
        print(f"Added to tracker (application ID {app_id}).")

STATUSES = ["planned", "applied", "interview", "rejected", "offer"]

def edit_application():
    """Ask which application to change and update it."""
    app_id = input("\nApplication ID to update (Enter = quit): ").strip()
    if not app_id:
        return False
    status = input(f"New status {STATUSES} (Enter = keep): ").strip().lower()
    fields = {}
    if status in STATUSES:
        fields["status"] = status
        if status == "applied":
            fields["applied_at"] = date.today()
        if status == "interview":
            fields["interview_invited"] = True
            day = input("Interview date YYYY-MM-DD (Enter = unknown): ").strip()
            if day:
                fields["interview_date"] = day
        if status == "offer":
            fields["accepted"] = "yes"
        if status == "rejected":
            fields["accepted"] = "no"
    if fields:
        update_application(int(app_id), **fields)
        print("Updated.")
    return True

if __name__ == "__main__":
    # Ask once; Enter keeps the default user
    user_id = input("User ID: ").strip()
    show_recommendations(user_id)
    ask_feedback(user_id)
    ask_add(user_id)
    show_tracker(user_id)
    while edit_application():
        show_tracker(user_id)