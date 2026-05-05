# WMSU Online Examination System (OES)

A Flask-based exam management platform for Western Mindanao State University — teachers create subjects/exams with AI-generated questions, students take timed exams, and admins manage users system-wide.

## Run & Operate

- **Start**: `python app.py` (workflow: "Start application", port 5000)
- **Default accounts**: `teacher@example.com / teacher123`, `admin@example.com / admin123`
- **Teacher registration code**: `ADMIN123`

### Required env vars
| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini 1.5 Flash AI question generation (already set) |
| `DATABASE_URL` | Neon PostgreSQL connection string (optional; falls back to SQLite) |
| `CLERK_PUBLISHABLE_KEY` | Clerk Google OAuth (optional) |
| `CLERK_SECRET_KEY` | Clerk Google OAuth (optional) |
| `FLASK_SECRET_KEY` | Flask session secret (has a default) |

## Stack

- **Runtime**: Python 3.12, Flask 3.x
- **Database**: SQLite (dev fallback) or Neon PostgreSQL (production via `DATABASE_URL`)
- **AI**: Google Generative AI `gemini-1.5-flash` via `google-generativeai`
- **Auth**: bcrypt password hashing + optional Clerk Google OAuth
- **Frontend**: Tailwind CSS CDN, Font Awesome 6, Inter + Cinzel (Google Fonts)
- **File processing**: pandas (CSV/Excel student uploads)

## Where things live

- `app.py` — all routes, DB init, Gemini integration, Clerk OAuth callback
- `templates/base.html` — shared Tailwind layout (sidebar auth / public card)
- `templates/` — 18 Jinja2 templates (all redesigned)
- `static/img/` — `wmsu_logo.png`, `wmsu_campus.png`
- `static/css/style.css` — minimal legacy overrides (Tailwind handles everything)
- `uploads/` — temporary CSV/Excel uploads (auto-deleted after processing)

## Architecture decisions

- **Dual-DB pattern**: `get_db()` / `db_execute()` helper with `?→%s` auto-conversion supports both SQLite and PostgreSQL from same query strings; activated by `DATABASE_URL` env var
- **Gemini over Anthropic**: switched to `google.generativeai` with structured prompt parsing (regex block extraction)
- **Tailwind CDN**: configured with custom `maroon`/`gold` color scales in inline `tailwind.config`; no build step needed
- **Clerk OAuth**: optional overlay on top of existing email/password auth; `/auth/google/callback` verifies the Clerk JWT and looks up user by email
- **Single base template**: `base.html` uses `{% if session.user_id %}` to switch between sidebar (auth) and centered-card (public) layout; second `{% block content %}` use replaced with `{{ self.content() }}`

## Product

- **Teachers**: create subjects, build exams manually or via AI (Gemini), upload student lists (CSV/XLSX), verify students, view scored results
- **Students**: login by email or student number, take timed multiple-choice exams, view pass/fail prediction
- **Admins**: view system stats, manage teachers, delete subjects, view all students

## User preferences

- WMSU branding: maroon `#5a0000` + gold `#c9a227`
- Professional, mobile-first responsive design
- Gemini 1.5 Flash for AI question generation
- Neon PostgreSQL as production database

## Gotchas

- CSS `@media` selectors with `{#id` must have a space before `#` to avoid Jinja2 interpreting `{#` as a comment start
- bcrypt hashes stored as `str` in PostgreSQL (decoded), `bytes` in SQLite — `check_password()` normalizes both
- `INSERT OR IGNORE` (SQLite) must be `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL)
- Clerk Google OAuth requires `CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY`; feature is silently disabled if not set

## Pointers

- Gemini API: `google.generativeai` (deprecated but functional) — migrate to `google.genai` when ready
- Neon setup: Add PostgreSQL integration in Replit dashboard → `DATABASE_URL` auto-populated
- Clerk setup: clerk.com → create app → API Keys
