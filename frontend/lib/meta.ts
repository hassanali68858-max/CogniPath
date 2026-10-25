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
  balanced: { label: "Balanced", blurb: "Treats all three goals equally" },
  study_first: { label: "Study first", blurb: "Protects study time when time is short" },
  career_first: { label: "Career first", blurb: "Protects career steps when time is short" },
};

export const WEIGHT_WORDS = (w: number) =>
  w === 0 ? "Not at all" : w < 1 ? "A little" : w === 1 ? "Normal" : w < 2.5 ? "More" : "Top priority";
