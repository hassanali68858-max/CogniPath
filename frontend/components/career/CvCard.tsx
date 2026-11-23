"use client";

import { FileText, Loader2, Play, Upload } from "lucide-react";
import { useState } from "react";

import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { careerApi } from "@/lib/career";

/** Upload the CV (skills come only from the CV) and run the Career Agent pipeline. */
export function CvCard({ onPipelineDone }: { onPipelineDone: () => void }) {
  const { userId } = useUser();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [skills, setSkills] = useState<string[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);

  async function upload() {
    if (!file) return;
    setUploading(true);
    try {
      const r = await careerApi.uploadCv(userId, file);
      setSkills(r.skills);
      toast("success", "CV saved", `${r.skills.length} skills found in your CV.`);
    } catch (e) {
      toast("error", "Could not read the CV", errorText(e));
    } finally {
      setUploading(false);
    }
  }

  async function run() {
    setRunning(true);
    try {
      await careerApi.runPipeline(userId);
      toast("success", "Career Agent finished", "Your matches, plan and suggestions are updated.");
      onPipelineDone();
    } catch (e) {
      toast("error", "The pipeline failed", errorText(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <FileText size={18} className="muted" />
        <div className="grow">
          <h2>Your CV</h2>
          <p>Your skills are read only from your CV, never guessed.</p>
        </div>
      </div>

      <label className="dropzone">
        <Upload size={22} />
        <b>{file ? file.name : "Choose your CV (PDF)"}</b>
        <span className="small faint">Click to pick a file</span>
        <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>

      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn career" onClick={upload} disabled={!file || uploading}>
          {uploading ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
          {uploading ? "Reading your CV…" : "Upload CV"}
        </button>
      </div>

      {skills && (
        <div style={{ marginTop: 14 }}>
          <span className="field-label">Skills found in your CV</span>
          <div className="chips" style={{ marginTop: 6 }}>
            {skills.length ? skills.map((s) => <span key={s} className="skill-chip">{s}</span>) : <span className="faint small">No skills found.</span>}
          </div>
        </div>
      )}

      <hr style={{ border: 0, borderTop: "1px solid var(--border)", margin: "18px 0" }} />

      <div className="row">
        <div className="grow">
          <h3>Find new jobs</h3>
          <p className="small muted">Collects new postings, matches them to your CV and sends suggestions to the Planner.</p>
        </div>
        <button className="btn" onClick={run} disabled={running}>
          {running ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {running ? "Running… (a few minutes)" : "Run Career Agent"}
        </button>
      </div>
    </section>
  );
}
