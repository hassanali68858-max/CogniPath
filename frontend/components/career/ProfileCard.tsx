"use client";

import { Loader2, Save, Target } from "lucide-react";
import { useEffect, useState } from "react";

import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { type CareerProfile, careerApi } from "@/lib/career";

// Same choices as the Career Agent's Streamlit Profile tab
const JOB_TYPES = ["full-time", "part-time", "internship", "thesis", "trainee"];
const WORK_MODES = ["any", "remote", "hybrid", "onsite"];

const EMPTY: CareerProfile = { countries: [], job_types: [], work_mode: "any", target_title: "", interests: [] };
// "FI, SE" -> ["FI", "SE"]
const toList = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);

/** Job preferences a CV cannot tell us (country, job type, work mode, target title, interests). */
export function ProfileCard() {
  const { userId } = useUser();
  const toast = useToast();
  const [profile, setProfile] = useState<CareerProfile>(EMPTY);
  const [countries, setCountries] = useState("");
  const [interests, setInterests] = useState("");
  const [saving, setSaving] = useState(false);

  // Load the saved preferences of the current student
  useEffect(() => {
    careerApi
      .getProfile(userId)
      .then((p) => {
        setProfile(p);
        setCountries(p.countries.join(", "));
        setInterests(p.interests.join(", "));
      })
      .catch(() => setProfile(EMPTY));
  }, [userId]);

  const toggleType = (t: string) =>
    setProfile((p) => ({
      ...p,
      job_types: p.job_types.includes(t) ? p.job_types.filter((x) => x !== t) : [...p.job_types, t],
    }));

  async function save() {
    setSaving(true);
    try {
      const body = { ...profile, countries: toList(countries), interests: toList(interests) };
      await careerApi.saveProfile(userId, body);
      setProfile({ ...body, saved: true });
      toast("success", "Preferences saved", "Run the Career Agent to find jobs that fit them.");
    } catch (e) {
      toast("error", "Could not save", errorText(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <Target size={18} className="muted" />
        <div className="grow">
          <h2>Job preferences</h2>
          <p>What your CV cannot tell the agent. {profile.saved ? "" : "Nothing saved yet."}</p>
        </div>
      </div>

      <div className="fields">
        <label className="field">
          <span className="field-label">Target job title</span>
          <input
            value={profile.target_title}
            placeholder="e.g. Data Scientist"
            onChange={(e) => setProfile({ ...profile, target_title: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field-label">Countries</span>
          <input value={countries} placeholder="e.g. FI, SE" onChange={(e) => setCountries(e.target.value)} />
          <span className="field-hint">Comma separated country codes</span>
        </label>
      </div>

      <div className="field" style={{ marginTop: 14 }}>
        <span className="field-label">Job type</span>
        <div className="chips">
          {JOB_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip${profile.job_types.includes(t) ? " career-on" : ""}`}
              onClick={() => toggleType(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="field" style={{ marginTop: 14 }}>
        <span className="field-label">Work mode</span>
        <div className="segmented">
          {WORK_MODES.map((m) => (
            <button
              key={m}
              type="button"
              className={profile.work_mode === m ? "on" : ""}
              onClick={() => setProfile({ ...profile, work_mode: m })}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <label className="field" style={{ marginTop: 14 }}>
        <span className="field-label">Interests</span>
        <input value={interests} placeholder="e.g. AI, sustainability" onChange={(e) => setInterests(e.target.value)} />
      </label>

      <div className="row" style={{ marginTop: 16 }}>
        <button
          className="btn career"
          onClick={save}
          disabled={saving || !toList(countries).length || !profile.job_types.length}
        >
          {saving ? <Loader2 size={16} className="spin" /> : <Save size={16} />}
          Save preferences
        </button>
        <span className="field-hint">Country and job type are required.</span>
      </div>
    </section>
  );
}
