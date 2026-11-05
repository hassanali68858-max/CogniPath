// Names, colours and icons used everywhere in the UI.
import { BookOpen, Briefcase, GraduationCap, type LucideIcon, Ticket, TrendingUp, UserRound, Users } from "lucide-react";

import type { Goal, SourceAgent } from "./types";

export const AGENTS: Record<SourceAgent, { label: string; short: string; icon: LucideIcon; blurb: string }> = {
  event: { label: "Event Agent", short: "Event", icon: Ticket, blurb: "Finds events from websites, posters and emails" },
  tutor: { label: "Tutor Agent", short: "Tutor", icon: GraduationCap, blurb: "Course work, deadlines, quizzes, Erasmus" },
  career: { label: "Career Agent", short: "Career", icon: Briefcase, blurb: "Skill gaps, jobs, CV and applications" },
  user: { label: "You", short: "You", icon: UserRound, blurb: "Things you add yourself" },
};

export const GOAL_META: Record<Goal, { label: string; icon: LucideIcon; question: string }> = {
  study: { label: "Study", icon: BookOpen, question: "Courses, homework, exams" },
  career: { label: "Career", icon: TrendingUp, question: "Skills, CV, applications, networking" },
  social: { label: "Social", icon: Users, question: "Events, friends, student life" },
};

export const MODE_META: Record<string, { label: string; blurb: string }> = {
  balanced: { label: "Balanced", blurb: "Best compromise: no goal is left far behind its best" },
  lean_study: { label: "More study", blurb: "Gets study close to its best; the others give a little" },
  lean_career: { label: "More career", blurb: "Gets career close to its best; the others give a little" },
  lean_social: { label: "More social", blurb: "Gets social close to its best; the others give a little" },
  nimbus: { label: "Your adjustment", blurb: "Made from your improve / keep / can give choices" },
};

export const CLASS_META = {
  improve: { label: "Improve", hint: "Make this better" },
  keep: { label: "Keep", hint: "Don't let this get worse" },
  worsen: { label: "Can give", hint: "This may get worse to pay for it" },
} as const;
