import re

import requests
import streamlit as st

# Address of our FastAPI server (api.py must be running)
API_URL = "http://127.0.0.1:8000"
API_DOWN = "API is not running. Start it with: uvicorn api:app --reload"

st.title("CogniPath Career Agent")

# The user types their own id once; all tabs use it
user_id = st.text_input("User ID").strip()
if not user_id:
    st.info("Enter your User ID to start.")
    st.stop()


def match_percent(reason: str):
    """Find the match percent in the reason text ('Match 75%' or '75% match'). Returns N or None."""
    found = re.search(r"Match\s+(\d+)%|(\d+)%\s+match", reason, re.IGNORECASE)
    if not found:
        return None
    return int(found.group(1) or found.group(2))


def error_text(r, default="Something went wrong."):
    """Return the API error message safely, even if the body is not JSON."""
    try:
        return r.json().get("detail", default)
    except ValueError:  # JSONDecodeError is a subclass of ValueError
        return r.text or default


def api_post(path, body, timeout=300):
    """POST to the API. Return the JSON reply, or show an error and return None."""
    try:
        r = requests.post(f"{API_URL}{path}", json=body, timeout=timeout)
    except requests.RequestException:
        st.error(API_DOWN)
        return None
    if r.status_code != 200:
        st.error(error_text(r))
        return None
    return r.json()


def prepare_application(title):
    """Cover letter + tailored CV for one job, step by step. The human decides each step."""
    key = f"apply_{title}"
    state = st.session_state.get(key)

    # Not started yet: show only the button
    if state is None:
        if st.button("Prepare application", key=f"btn_{title}"):
            with st.spinner("Writing your cover letter... this can take a minute."):
                state = api_post(f"/apply/{user_id}/start", {"title": title})
            if state:
                st.session_state[key] = state
                st.rerun()
        return

    job_id = state["job_id"]

    # Finished: offer the files for download
    if state["status"] == "done":
        if not state.get("has_letter"):
            st.info("Stopped. No files were made.")
        else:
            st.success("Your files are ready. Read them carefully before you apply yourself.")
            for kind, label in (("letter", "Download cover letter"), ("cv", "Download tailored CV")):
                r = requests.get(f"{API_URL}/apply/{user_id}/{job_id}/file/{kind}", timeout=30)
                if r.status_code == 200:
                    st.download_button(label, r.content, file_name=f"{kind}_job{job_id}.docx",
                                       key=f"dl_{kind}_{title}")
        if st.button("Start again", key=f"reset_{title}"):
            del st.session_state[key]
            st.rerun()
        return

    # Paused: show what the graph is asking
    step = state["step"]
    for w in step.get("warnings", []):
        st.warning(w)

    if "question" in step:
        # Delivery: only download works for now
        choice = st.radio(step["question"], ["download"], key=f"del_{title}")
        if st.button("Continue", key=f"cont_{title}"):
            reply = api_post(f"/apply/{user_id}/{job_id}/answer", {"answer": choice})
            if reply:
                st.session_state[key] = reply
                st.rerun()
        return

    if "match" in step:
        st.write(step["match"])
        st.write("Missing skills: " + ", ".join(step["missing"]))
        hint = "Type yes to write a letter anyway, or no to stop."
    elif "letter" in step:
        st.markdown("**Cover letter**")
        st.text(step["letter"])
        hint = "Type yes to approve, edit: followed by your own letter, or write what to change."
    else:
        st.markdown("**CV profile**")
        st.text(step["summary"])
        if step["removed"]:
            st.write("Removed from your CV for this job:")
            for i, item in enumerate(step["removed"]):
                st.write(f"[{i}] {item[:90]}")
        hint = "Type yes to approve, restore 0 2 to bring items back, or write what to change."

    # A form clears the text box after sending
    with st.form(key=f"form_{title}", clear_on_submit=True):
        answer = st.text_area(hint)
        if st.form_submit_button("Send") and answer.strip():
            with st.spinner("Working..."):
                reply = api_post(f"/apply/{user_id}/{job_id}/answer", {"answer": answer.strip()})
            if reply:
                st.session_state[key] = reply
                st.rerun()


def tracker_buttons(title):
    """Save the job to the tracker, or mark it applied after the user applied themselves."""
    # Is this job already in the user's tracker?
    try:
        rows = requests.get(f"{API_URL}/tracker/{user_id}", timeout=10).json()
    except (requests.RequestException, ValueError):
        st.caption("Tracker not available right now.")
        return
    row = next((r for r in rows if r["title"] == title), None)

    if row and row["status"] != "planned":
        # Already applied (or further): just show the status
        st.caption(f"Tracker: {row['status']}")
        return

    col1, col2 = st.columns(2)
    if row is None and col1.button("Save to tracker", key=f"save_{title}"):
        api_post(f"/tracker/{user_id}", {"title": title, "applied": False})
        st.rerun()
    # The agent never applies: the user clicks this AFTER applying on the company site
    if col2.button("I applied", key=f"applied_{title}"):
        if row is None:
            api_post(f"/tracker/{user_id}", {"title": title, "applied": True})
        else:
            requests.patch(f"{API_URL}/tracker/{user_id}/{row['application_id']}",
                           json={"status": "applied"}, timeout=10)
        st.rerun()


tab_profile, tab_cv, tab_plan, tab_track = st.tabs(["1. Profile", "2. CV", "3. My Plan", "4. My applications"])

# ---------- Tab 1: job preferences (a CV cannot tell us these) ----------
with tab_profile:
    countries = st.multiselect("Countries", ["FI", "SE", "NO", "DK", "DE", "NL", "EE"])
    job_types = st.multiselect("Job type", ["full-time", "part-time", "internship", "thesis", "trainee"])
    work_mode = st.selectbox("Work mode", ["any", "remote", "hybrid", "onsite"])
    target_title = st.text_input("Target job title (e.g. Data Scientist)")
    interests = st.text_input("Interests (comma separated)")

    if st.button("Save profile"):
        profile = {
            "countries": countries,
            "job_types": job_types,
            "work_mode": work_mode,
            "target_title": target_title.strip(),
            "interests": [i.strip() for i in interests.split(",") if i.strip()],
        }
        try:
            r = requests.post(f"{API_URL}/profile/{user_id}", json=profile, timeout=10)
        except requests.RequestException:
            st.error(API_DOWN)
        else:
            if r.status_code == 200:
                st.success(f"Saved preferences for {user_id}")
            else:
                st.error(error_text(r, "Could not save profile."))

# ---------- Tab 2: upload the CV; skills are read from it ----------
with tab_cv:
    st.write("Upload your CV as a PDF. Your skills are read only from your CV.")
    cv_file = st.file_uploader("CV (PDF)", type=["pdf"])

    if cv_file is not None and st.button("Upload CV"):
        with st.spinner("Reading your CV... this can take a minute."):
            try:
                r = requests.post(
                    f"{API_URL}/cv/{user_id}",
                    files={"file": (cv_file.name, cv_file.getvalue(), "application/pdf")},
                    timeout=600,
                )
            except requests.RequestException:
                st.error(API_DOWN)
                r = None
        if r is not None:
            if r.status_code == 200:
                st.success("CV saved. Skills found in your CV:")
                st.write(", ".join(r.json()["skills"]) or "No skills found.")
            else:
                st.error(error_text(r, "Could not read the CV."))

# ---------- Tab 4: application tracker (the user updates it, the agent never applies) ----------
# Placed before Tab 3 because Tab 3 may call st.stop()
with tab_track:
    STATUS_COLORS = {"planned": "gray", "applied": "green", "interview": "blue",
                     "offer": "violet", "rejected": "red"}
    try:
        rows = requests.get(f"{API_URL}/tracker/{user_id}", timeout=10).json()
    except (requests.RequestException, ValueError):
        st.error(API_DOWN)
        rows = []

    if not rows:
        st.info("No applications yet. Use 'Save to tracker' or 'I applied' on a job in My Plan.")
    for r in rows:
        with st.container(border=True):
            color = STATUS_COLORS.get(r["status"], "gray")
            st.markdown(f"### {r['title']}  :{color}-background[{r['status']}]")
            match = f"{round(r['match'] * 100)}% match" if r["match"] is not None else "match -"
            st.caption(f"{r['company'] or '-'} · {match} · Deadline: {r['deadline'] or '-'}")
            st.write(f"Interview invitation: {'Yes' if r['interview_invited'] else 'No'}"
                     f" · Accepted: {r['accepted']}"
                     f" · Interview: {r['interview_date'] or '-'}")

            # Small form to change the status
            with st.form(key=f"track_{r['application_id']}"):
                statuses = list(STATUS_COLORS)
                new_status = st.selectbox("Status", statuses, index=statuses.index(r["status"])
                                          if r["status"] in statuses else 0)
                day = st.date_input("Interview date (only for interview)", value=None)
                if st.form_submit_button("Update"):
                    body = {"status": new_status,
                            "interview_date": day.isoformat() if day else None}
                    resp = requests.patch(f"{API_URL}/tracker/{user_id}/{r['application_id']}",
                                          json=body, timeout=10)
                    if resp.status_code == 200:
                        st.rerun()
                    else:
                        st.error(error_text(resp, "Could not update."))

# ---------- Tab 3: run the pipeline and show the plan ----------
# This tab is last, so st.stop() here does not hide the other tabs
with tab_plan:
    if st.button("Run pipeline"):
        with st.spinner("Running the Career Agent... this can take a few minutes."):
            try:
                run = requests.post(f"{API_URL}/run/{user_id}", timeout=900)
            except requests.RequestException:
                st.error(API_DOWN)
                st.stop()
        if run.status_code == 200:
            st.success("Pipeline finished. Your new plan is below.")
        else:
            st.error(error_text(run, "Pipeline failed."))
            st.stop()

    try:
        response = requests.get(f"{API_URL}/plan/{user_id}", timeout=10)
    except requests.RequestException:
        st.error(API_DOWN)
        st.stop()

    # 404 = no plan for this user yet
    if response.status_code != 200:
        st.warning(error_text(response, "No plan yet. Click Run pipeline."))
        st.stop()

    plan = response.json()
    st.caption(f"User: {plan['user_id']} | Generated: {plan['generated_at'][:16]}")

    # One section per proposal type
    SECTIONS = {"application": "Apply", "learning": "Learn", "event": "Events"}
    for ptype, heading in SECTIONS.items():
        items = [p for p in plan["proposals"] if p["type"] == ptype]
        st.header(f"{heading} ({len(items)})")
        for p in items:
            with st.container(border=True):
                st.subheader(p["title"])
                match = match_percent(p["reason"])
                if match is not None:
                    # Progress bar shows how well the CV matches this job
                    st.progress(min(match, 100) / 100, text=f"Match {match}%")
                st.write(p["reason"])
                st.caption(f"Career value: {p['value']['career']} | Priority: {p['priority']}")
                if ptype == "application":
                    prepare_application(p["title"].removeprefix("Apply: "))
                    tracker_buttons(p["title"].removeprefix("Apply: "))