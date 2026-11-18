'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, CheckCircle2, X } from 'lucide-react';
import type { TutorProgress, WeakTopic } from '@/lib/cognipath/types';
import { cn } from '@/lib/cognipath/theme';

function QuizModal({ topic, onClose }: { topic: WeakTopic; onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const q = topic.questions[index];
  const done = index >= topic.questions.length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  function choose(i: number) {
    if (picked !== null) return;
    setPicked(i);
    if (i === q.answerIndex) setScore((s) => s + 1);
  }
  function next() { setPicked(null); setIndex((i) => i + 1); }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={`Practice quiz: ${topic.topic}`} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{topic.topic}</h3>
            <p className="text-xs text-slate-500">{topic.course}{!done && ` · Question ${index + 1} of ${topic.questions.length}`}</p>
          </div>
          <button onClick={onClose} aria-label="Close quiz" className="rounded p-1 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4" /></button>
        </div>

        {done ? (
          <div className="mt-6 text-center">
            <CheckCircle2 className="mx-auto h-10 w-10 text-blue-500" />
            <p className="mt-3 text-lg font-semibold text-slate-900">You got {score} of {topic.questions.length}</p>
            <p className="mt-1 text-sm text-slate-600">
              {score === topic.questions.length ? 'Nice work. This topic moves out of your weak list after the next plan.' : 'The planner will keep a short review block for this topic.'}
            </p>
            <button onClick={onClose} className="mt-5 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Done</button>
          </div>
        ) : (
          <>
            <p className="mt-5 text-sm font-medium text-slate-900">{q.prompt}</p>
            <div className="mt-3 space-y-2">
              {q.options.map((opt, i) => {
                const correct = picked !== null && i === q.answerIndex;
                const wrong = picked === i && i !== q.answerIndex;
                return (
                  <button key={opt} onClick={() => choose(i)} disabled={picked !== null}
                    className={cn('w-full rounded-xl border px-3 py-2 text-left text-sm transition-colors',
                      correct ? 'border-green-500 bg-green-50 text-green-900' : wrong ? 'border-red-400 bg-red-50 text-red-900' : 'border-slate-200 hover:border-blue-400 hover:bg-blue-50')}>
                    {opt}
                  </button>
                );
              })}
            </div>
            {picked !== null && (
              <div className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                <p>{q.explanation}</p>
                <button onClick={next} className="mt-3 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700">
                  {index + 1 === topic.questions.length ? 'See result' : 'Next question'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function TutorProgressCard({ data, className }: { data: TutorProgress; className?: string }) {
  const [quizTopic, setQuizTopic] = useState<WeakTopic | null>(null);
  const done = data.credits.reduce((s, c) => s + c.done, 0);
  const total = data.credits.reduce((s, c) => s + c.total, 0);

  return (
    <section className={cn('rounded-2xl bg-white p-6 ring-1 ring-slate-900/5', className)} aria-label="Study progress">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
        <h2 className="font-display text-lg font-semibold text-slate-900">Study progress</h2>
      </div>
      <p className="mt-0.5 text-xs text-slate-500">{data.programme}</p>

      {data.graduation.atRisk && (
        <div role="alert" className="mt-4 flex gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div className="text-sm">
            <p className="font-semibold text-amber-900">At risk: graduation {data.graduation.target}</p>
            <p className="mt-0.5 text-amber-800">Projected {data.graduation.projected}. {data.graduation.message}</p>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-3">
        {data.credits.map((c) => (
          <div key={c.label}>
            <div className="flex justify-between text-sm"><span className="font-medium text-slate-800">{c.label}</span><span className="tabular-nums text-slate-600">{c.done}/{c.total} credits</span></div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-blue-100" role="progressbar" aria-valuenow={c.done} aria-valuemin={0} aria-valuemax={c.total} aria-label={`${c.label} credits`}>
              <div className="h-full rounded-full bg-blue-500" style={{ width: `${(c.done / c.total) * 100}%` }} />
            </div>
          </div>
        ))}
        <p className="text-xs text-slate-500">{done} of {total} credits complete</p>
      </div>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <h3 className="text-sm font-semibold text-slate-900">Topics to strengthen</h3>
        <ul className="mt-2 space-y-2">
          {data.weakTopics.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
              <div className="min-w-0"><p className="truncate text-sm font-medium text-slate-800">{t.topic}</p><p className="text-xs text-slate-500">{t.course} · {t.mastery}% mastery</p></div>
              <button onClick={() => setQuizTopic(t)} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
                <BookOpen className="h-3.5 w-3.5" /> Start practice quiz
              </button>
            </li>
          ))}
        </ul>
      </div>

      {quizTopic && <QuizModal topic={quizTopic} onClose={() => setQuizTopic(null)} />}
    </section>
  );
}