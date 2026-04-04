"""Prompt builder for the curriculum planning agent."""

from __future__ import annotations


def build_planner_prompt(
    student_profile: dict,
    work_dir: str,
    has_guide: bool,
) -> str:
    semesters = student_profile.get("target_semesters", 4)
    interests = ", ".join(student_profile.get("interests", []))
    completed = ", ".join(student_profile.get("completed_codes", [])) or "None"
    program = student_profile.get("program_slug", "not specified")

    guide_section = ""
    if has_guide:
        guide_section = """
- `guide_pages.json` — Extracted content from the uploaded course guide PDF.
  Contains page-by-page text, tables, and layout classification.
  Pay special attention to pages with layout_type "curriculum_map" or "requirements"."""

    return f"""You are a McGill University academic advisor building a realistic curriculum plan.

## Student Profile
- Interests: {interests}
- Program: {program}
- Completed courses: {completed}
- Planning horizon: {semesters} semesters

## Available Files in Your Working Directory

Read these files to understand the student's options:

- `student_profile.json` — Full student profile with interests, completed courses, and constraints.
- `program_requirements.json` — Required and elective courses for the student's program.
- `candidate_courses.json` — Courses from the database matching the student's interests and program.
  Each entry has: code, title, credits, dept, faculty, terms (when offered), description,
  prerequisites_raw, restrictions_raw.{guide_section}

## Your Task

Build a {semesters}-semester curriculum plan. For each semester:

1. **Read** the context files to understand available courses, requirements, and prerequisites.
2. **Reason** about prerequisite chains — ensure prerequisites are scheduled before the courses that need them.
3. **Check term availability** — the `terms` field shows when courses are offered (Fall, Winter, Summer).
   Map semesters chronologically: Semester 1 = Fall, Semester 2 = Winter, Semester 3 = Fall, etc.
4. **Balance credit load** — aim for 12-15 credits per semester (4-5 courses of 3 credits each).
5. **Prioritize** required courses first, then electives aligned with student interests.
6. **Avoid conflicts** — check restrictions_raw for courses that cannot be taken together.

## Output

Write TWO files:

1. `curriculum_plan.md` — A formatted markdown document with:
   - Summary of the plan rationale
   - Semester-by-semester breakdown with course codes, titles, and credits
   - Total credits per semester
   - Notes on prerequisite chains and any scheduling considerations
   - Suggested alternatives if a course is unavailable

2. `curriculum_plan.json` — A structured JSON file:
```json
{{
  "semesters": [
    {{
      "term": "Fall 2026",
      "courses": [
        {{"code": "COMP 250", "title": "Intro to Computer Science", "credits": 3.0}},
        ...
      ],
      "total_credits": 15.0
    }},
    ...
  ],
  "total_credits": 60.0,
  "notes": ["prerequisite chain: COMP 202 → COMP 250 → COMP 251", ...]
}}
```

Start by reading all the context files, then build the plan systematically."""
