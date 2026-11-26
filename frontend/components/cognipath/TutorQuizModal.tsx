'use client';

import { useEffect, useState } from 'react';
import { Check, CheckCircle2, Loader2, X } from 'lucide-react';
import { tutorApi, type QuizResult, type QuizView, type TopicStatus, type TutorContext } from '@/lib/cognipath/tutor-api';
import { cn } from '@/lib/cognipath/theme';

type Props = { topic: TopicStatus; context: TutorContext; onGraded: () => void; onClose: () => void };

/** A quiz made and graded by the Tutor backend; the answers are only known after grading. */
export default function TutorQuizModal({ topic, context, onGraded, onClose }: Props) {
  const [quiz, setQuiz] = useState<QuizView | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [index, setIndex] = useState(0);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    tutorApi.newQuiz(context, topic.topic_id).then(
      (q) => { setQuiz(q); setAnswers(q.questions.map(() => null)); },
      (e: Error) => setError(e.message),
    );
  }, [context, topic.topic_id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function submit() {
    if (!quiz) return;
    setBusy(true);
    try {
      setResult(await tutorApi.submitAnswers(context, quiz.quiz_id, answers as number[]));
      onGraded();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const total = quiz?.questions.length ?? 0;
  const q = quiz?.questions[index];
  const isLast = index === total - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={`Practice quiz: ${topic.name}`} className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{topic.name}</h3>
            <p className="text-xs text-slate-500">{topic.course_code}{quiz && !result && ` · Question ${index + 1} of ${total}`}</p>
          </div>
          <button onClick={onClose} aria-label="Close quiz" className="rounded border-0 bg-transparent p-1 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4" /></button>
        </div>

        {error && <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {!quiz && !error && <Loader2 className="mx-auto mt-8 h-6 w-6 animate-spin text-blue-500" aria-label="Making your quiz" />}

        {quiz && result && <QuizReview quiz={quiz} answers={answers as number[]} result={result} onClose={onClose} />}

        {quiz && q && !result && (
          <>
            <p className="mt-5 text-sm font-medium text-slate-900">{q.prompt}</p>
            <div className="mt-3 space-y-2" role="radiogroup" aria-label={q.prompt}>
              {q.options.map((opt, i) => (
                <button key={opt} role="radio" aria-checked={answers[index] === i} onClick={() => setAnswers((a) => a.map((v, n) => (n === index ? i : v)))}
                  className={cn('w-full rounded-xl border px-3 py-2 text-left text-sm transition-colors',
                    answers[index] === i ? 'border-blue-500 bg-blue-50 text-blue-950' : 'border-slate-200 bg-white hover:border-blue-400 hover:bg-blue-50')}>
                  {opt}
                </button>
              ))}
            </div>
            <div className="mt-5 flex justify-between">
              <button onClick={() => setIndex((i) => i - 1)} disabled={index === 0} className="rounded-lg border-0 bg-transparent px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:invisible">Back</button>
              <button onClick={isLast ? submit : () => setIndex((i) => i + 1)} disabled={answers[index] === null || busy}
                className="inline-flex items-center gap-1.5 rounded-lg border-0 bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {isLast ? 'Check my answers' : 'Next question'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function QuizReview({ quiz, answers, result, onClose }: { quiz: QuizView; answers: number[]; result: QuizResult; onClose: () => void }) {
  const before = result.mastery_before === null ? 'not tested' : percent(result.mastery_before);
  return (
    <div className="mt-5">
      <div className="text-center">
        <CheckCircle2 className="mx-auto h-10 w-10 text-blue-500" />
        <p className="mt-3 text-lg font-semibold text-slate-900">You got {result.correct} of {result.total}</p>
        <p className="mt-1 text-sm text-slate-600">Topic mastery: {before} → {percent(result.mastery_after)}. Your Tutor suggestions are updated.</p>
      </div>
      <ol className="mt-5 list-none space-y-3 pl-0">
        {quiz.questions.map((q, qi) => {
          const right = answers[qi] === result.answer_indexes[qi];
          return (
            <li key={qi} className={cn('rounded-xl border p-3 text-sm', right ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50')}>
              <p className="font-medium text-slate-900">{q.prompt}</p>
              <p className={cn('mt-1 flex gap-1.5', right ? 'text-green-900' : 'text-red-900')}>
                {right ? <Check className="mt-0.5 h-4 w-4 shrink-0" /> : <X className="mt-0.5 h-4 w-4 shrink-0" />}
                Your answer: {q.options[answers[qi]]}
              </p>
              {!right && <p className="mt-1 pl-5.5 text-green-900">Correct: {q.options[result.answer_indexes[qi]]}</p>}
            </li>
          );
        })}
      </ol>
      <button onClick={onClose} className="mt-5 w-full rounded-xl border-0 bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Done</button>
    </div>
  );
}

export const percent = (share: number) => `${Math.round(share * 100)}%`;
