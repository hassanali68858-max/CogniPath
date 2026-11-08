import streamlit as st
from db import save_user_profile

st.title("CogniPath - Your job preferences")

# Skills come from the CV; here we only ask what a CV cannot tell us
user_id = st.text_input("Your username")
countries = st.multiselect("Countries", ["FI", "SE", "NO", "DK", "DE", "NL", "EE"])
job_types = st.multiselect("Job type", ["full-time", "part-time", "internship", "thesis", "trainee"])
work_mode = st.selectbox("Work mode", ["any", "remote", "hybrid", "onsite"])
target_title = st.text_input("Target job title (e.g. Data Scientist)")
interests = st.text_input("Interests (comma separated)")

if st.button("Save"):
    if not user_id or not countries or not job_types:
        st.error("Username, country and job type are required.")
    else:
        interest_list = [i.strip() for i in interests.split(",") if i.strip()]
        save_user_profile(user_id, countries, job_types, work_mode, target_title, interest_list)
        st.success(f"Saved preferences for {user_id}")