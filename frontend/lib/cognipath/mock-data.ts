import type { ActivityProposal, AgentSource, ChangeTag, InternshipMatch, PlanVersion, ScheduledItem } from './types';

export const WEEK_START = '2026-11-02'; // Monday
export const TODAY = '2026-11-04';
export const NOW = '2026-11-04T11:20';

const at = (day: number, hhmm: string) => `2026-11-0${day}T${hhmm}`;

function mk(
  id: string, source: AgentSource, type: ActivityProposal['type'], title: string, reason: string,
  value: ActivityProposal['value'], extra: Partial<ActivityProposal> = {},
): ActivityProposal {
  return { proposal_id: id, source_agent: source, user_id: 'u1', type, title, reason, value, ...extra };
}

const P: Record<string, ActivityProposal> = {
  'lec-ml': mk('lec-ml', 'user', 'course_work', 'Machine Learning lecture', 'Fixed lecture from your course timetable.', { study: 5 }, { hard: true, location: 'Agora, room 2', fixed_time: { start: at(2, '10:00'), end: at(2, '12:00') } }),
  'lec-db': mk('lec-db', 'user', 'course_work', 'Databases lecture', 'Fixed lecture from your course timetable.', { study: 5 }, { hard: true, location: 'Mattilanniemi, MaD 201', fixed_time: { start: at(4, '12:00'), end: at(4, '14:00') } }),
  'shift-tue': mk('shift-tue', 'user', 'other', 'Work shift: campus café', 'Your recurring work shift. Nothing else can be planned here.', {}, { hard: true, fixed_time: { start: at(3, '16:00'), end: at(3, '20:00') } }),
  'shift-fri': mk('shift-fri', 'user', 'other', 'Work shift: campus café', 'Your recurring work shift. Nothing else can be planned here.', {}, { hard: true, fixed_time: { start: at(6, '16:00'), end: at(6, '20:00') } }),
  meetup: mk('meetup', 'event', 'event', 'AI & Data meetup', 'Matches your interest in applied AI, and two speakers are hiring for internships.', { social: 6, career: 3 }, { location: 'Startup Hub', resource_url: 'https://example.com/ai-meetup', fixed_time: { start: at(5, '17:30'), end: at(5, '19:30') } }),
  board: mk('board', 'event', 'social', 'Board game night', 'Low-key social evening you marked as a goal this month.', { social: 5 }, { location: 'Student union', fixed_time: { start: at(7, '18:00'), end: at(7, '21:00') } }),
  hike: mk('hike', 'event', 'social', 'Sunday hike at Laajavuori', 'Fresh air after a heavy study week keeps your social goal on track.', { social: 5 }, { location: 'Laajavuori trailhead', fixed_time: { start: at(8, '11:00'), end: at(8, '13:00') } }),
  quiz: mk('quiz', 'tutor', 'quiz', 'Practice quiz: probability', 'Probability is your weakest topic and the ML exam is in 9 days.', { study: 6 }, { duration_min: 60, priority: 'high' }),
  thesis: mk('thesis', 'tutor', 'course_work', 'Thesis literature review block', 'Keeps the thesis outline on pace for the December supervisor meeting.', { study: 8 }, { duration_min: 120, priority: 'high' }),
  report: mk('report', 'tutor', 'course_work', 'Databases project report', 'The report is due next Monday and needs about two hours of focused writing.', { study: 8 }, { duration_min: 120, priority: 'high', window: { earliest: at(2, '08:00'), deadline: at(8, '23:00') } }),
  rdf: mk('rdf', 'tutor', 'learning', 'RDF and knowledge graphs reading', 'Background reading that supports both your thesis and the AI Thesis role.', { study: 4, career: 3 }, { duration_min: 90, resource_url: 'https://example.com/rdf-primer' }),
  docker: mk('docker', 'career', 'learning', 'Docker fundamentals course', 'Docker is missing from 3 of your top internship matches.', { career: 6 }, { duration_min: 90, resource_url: 'https://example.com/docker-course' }),
  langgraph: mk('langgraph', 'career', 'learning', 'LangGraph tutorial', 'LangGraph appears in the Aalto AI Thesis requirements.', { career: 6 }, { duration_min: 90, resource_url: 'https://example.com/langgraph' }),
  apply: mk('apply', 'career', 'application', 'Submit AI Thesis application', 'The application closes Friday, so this has to land before then.', { career: 9 }, { duration_min: 60, priority: 'high', window: { earliest: at(2, '08:00'), deadline: at(6, '12:00') } }),
  cv: mk('cv', 'career', 'other', 'Update CV for internships', 'Your CV has not been updated since August and applications are coming up.', { career: 5 }, { duration_min: 60 }),
};

const slot = (v: string, key: string, day: number, from: string, to: string, tag: ChangeTag = 'UNCHANGED'): ScheduledItem => ({
  id: `${v}-${key}`, proposal: P[key], assigned_start: at(day, from), assigned_end: at(day, to),
  status: P[key].hard ? 'accepted' : 'pending', change_tag: tag,
});

const fixed = (v: string): ScheduledItem[] => [
  slot(v, 'lec-ml', 2, '10:00', '12:00'),
  slot(v, 'shift-tue', 3, '16:00', '20:00'),
  slot(v, 'lec-db', 4, '12:00', '14:00'),
  slot(v, 'meetup', 5, '17:30', '19:30'),
  slot(v, 'shift-fri', 6, '16:00', '20:00'),
];

export const MOCK_PLANS: PlanVersion[] = [
  {
    id: 'plan-balanced', version_type: 'balanced',
    kept_percentages: { study: 100, career: 100, social: 65 },
    items: [
      ...fixed('b'),
      slot('b', 'cv', 2, '13:00', '14:00'),
      slot('b', 'quiz', 3, '09:00', '10:00'),
      slot('b', 'thesis', 4, '14:30', '16:30', 'MOVED'),
      slot('b', 'docker', 5, '10:00', '11:30', 'NEW'),
      slot('b', 'apply', 5, '13:00', '14:00'),
      slot('b', 'report', 6, '09:00', '11:00'),
      slot('b', 'langgraph', 7, '10:00', '11:30'),
      slot('b', 'board', 7, '18:00', '21:00'),
    ],
    dropped_items: [P.rdf, P.hike],
  },
  {
    id: 'plan-study', version_type: 'study_first',
    kept_percentages: { study: 100, career: 70, social: 40 },
    items: [
      ...fixed('s'),
      slot('s', 'cv', 2, '13:00', '14:00'),
      slot('s', 'quiz', 3, '09:00', '10:00'),
      slot('s', 'thesis', 3, '12:00', '14:00', 'MOVED'),
      slot('s', 'rdf', 4, '15:00', '16:30', 'NEW'),
      slot('s', 'apply', 5, '13:00', '14:00'),
      slot('s', 'report', 5, '09:00', '11:00'),
      slot('s', 'board', 7, '18:00', '21:00'),
    ],
    dropped_items: [P.docker, P.langgraph, P.hike],
  },
  {
    id: 'plan-career', version_type: 'career_first',
    kept_percentages: { study: 85, career: 100, social: 55 },
    items: [
      ...fixed('c'),
      slot('c', 'apply', 2, '13:00', '14:00', 'MOVED'),
      slot('c', 'cv', 3, '09:00', '10:00'),
      slot('c', 'docker', 3, '10:30', '12:00', 'NEW'),
      slot('c', 'langgraph', 4, '15:00', '16:30', 'NEW'),
      slot('c', 'thesis', 5, '10:00', '12:00'),
      slot('c', 'report', 6, '09:00', '11:00'),
      slot('c', 'hike', 8, '11:00', '13:00'),
    ],
    dropped_items: [P.quiz, P.rdf, P.board],
  },
];

export const DROP_REASONS: Record<string, string> = {
  rdf: 'Clash with work shift: the only free slot this week overlaps your Tuesday café shift.',
  hike: 'Not enough free time: the Sunday slot would leave no buffer before the project report is due.',
  docker: 'Lower priority than study this week: every slot that fits your deadlines was taken by higher-value work.',
  langgraph: 'Lower priority than study this week: it can move to next week without affecting any deadline.',
  quiz: 'Study is not the focus of this version, and the quiz has no hard deadline yet.',
  board: 'Clash with Career First goals: the evening was needed to keep application prep on schedule.',
};

export const MOCK_MATCHES: InternshipMatch[] = [
  {
    id: 'aalto', title: 'AI Thesis Internship', org: 'Aalto University', deadline: 'Fri 6 Nov', match: 33,
    matchedSkills: ['Python', 'Machine learning'],
    missingSkills: ['Docker', 'LangGraph', 'RDF'],
    coverLetter: 'Dear Aalto AI team,\n\nI am a master’s student in Information Technology writing my thesis on applied AI, and I would love to join your thesis internship. I have hands-on experience with Python and machine learning from my coursework, and I am currently learning LangGraph and Docker so I can contribute to agent-based systems from the first week.\n\nWhat draws me to this role is the chance to work on real research problems with people who care about clear, reproducible work. I would bring curiosity, steady communication and a habit of finishing what I start.\n\nThank you for your time.\nBest regards',
  },
  {
    id: 'reaktor', title: 'Frontend Developer Intern', org: 'Reaktor', deadline: 'Sun 15 Nov', match: 72,
    matchedSkills: ['React', 'TypeScript', 'Next.js', 'Tailwind CSS'],
    missingSkills: ['GraphQL', 'Testing Library'],
    coverLetter: 'Dear Reaktor hiring team,\n\nI build production React and Next.js interfaces in TypeScript, and I enjoy turning messy backend data into screens people can actually use. Alongside my master’s studies I have been integrating APIs into an admin panel and a mobile app, so I am used to shipping with a team.\n\nGraphQL and Testing Library are the two gaps I am closing right now, and I would be glad to learn them on real projects with you.\n\nBest regards',
  },
];