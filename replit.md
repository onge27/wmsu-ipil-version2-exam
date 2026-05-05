# WMSU Online Examination System (OES)

A Flask-based exam management platform for Western Mindanao State University — teachers create subjects/exams with AI-generated questions, students request exam access (or use teacher-generated keys), take timed exams, and admins manage users system-wide.

## Run & Operate

- **Start**: `python app.py` (workflow: "Start application", port 5000)
- **Default accounts**: `teacher@example.com / teacher123`, `admin@example.com / admin123`
- **Teacher registration code**: `ADMIN123`

### Required env vars
| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini 1.5 Flash AI question generation (set) |
| `NEON_DATABASE_URL` | Neon PostgreSQL connection string (set) |
| `CLERK_PUBLISHABLE_KEY` | Clerk Google OAuth (set) |
| `CLERK_SECRET_KEY` | Clerk Google OAuth (set) |
| `FLASK_SECRET_KEY` | Flask session secret (has default) |

## Stack

- **Runtime**: Python 3.12, Flask 3.x
- **Database**: Neon PostgreSQL (`NEON_DATABASE_URL`) or SQLite fallback
- **AI**: Google Generative AI `gemini-1.5-flash`
- **Auth**: bcrypt + optional Clerk Google OAuth
- **Frontend**: Tailwind CSS CDN, Font Awesome 6, Inter + Cinzel (Google Fonts)
- **File processing**: pandas (CSV/Excel student uploads)

## Where things live

- `app.py` — all routes, DB init, Gemini, Clerk OAuth
- `templates/base.html` — shared layout (sidebar auth / public card)
- `templates/student_dashboard.html` — exam list with request/key access UI
- `templates/teacher_dashboard.html` — dashboard with pending requests alert
- `templates/exam_requests.html` — teacher approve/reject access requests
- `templates/exam_keys.html` — teacher generate/manage exam access keys
- `templates/` — 20 total Jinja2 templates
- `static/img/` — `wmsu_logo.png`, `wmsu_campus.png`

## Architecture decisions

- **Dual-DB**: `get_db()` / `db_execute()` with `?→%s` auto-conversion; uses `NEON_DATABASE_URL` (since `DATABASE_URL` is runtime-managed by Replit)
- **Exam Access Flow**: Students request access per exam → teacher approves; OR teacher generates a shareable key → student enters key for instant approval
- **Gemini over Anthropic**: `google.generativeai` with regex block extraction
- **Tailwind CDN**: custom `maroon`/`gold` color scales in inline config; no build step
- **Clerk OAuth**: optional overlay; `/auth/google/callback` verifies JWT, looks up user by email

## Product

- **Teachers**: create subjects/exams, AI-generate questions, manage access requests, generate exam access keys, upload student lists, view results
- **Students**: request exam access or use teacher-provided key, take timed exams, view pass/fail prediction
- **Admins**: system stats, manage teachers/subjects/students

## User preferences

- WMSU branding: maroon `#5a0000` + gold `#c9a227`
- Professional, mobile-first responsive design
- Year: 2026
- Neon PostgreSQL as production database

## Gotchas

- `DATABASE_URL` is runtime-managed by Replit — use `NEON_DATABASE_URL` instead
- CSS `{#id` must have space before `#` to avoid Jinja2 comment parsing
- bcrypt hashes: `str` in PostgreSQL, `bytes` in SQLite — `check_password()` normalizes
- `INSERT OR IGNORE` (SQLite) → `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL)
- Exam access requires approved `exam_access_requests` record; take_exam checks this

## Pointers

- Gemini: `google.generativeai` — migrate to `google.genai` when ready
- Clerk: clerk.com → app → API Keys
