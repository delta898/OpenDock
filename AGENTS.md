# OpenDock Agent Guidance

## Development journal and BlogGenius seeds

OpenDock is developed together with the user, who may turn meaningful parts of
that work into articles with BlogGenius. Treat the reasoning, failed attempts,
tradeoffs, operational lessons, and user-facing outcomes as potential material,
not only the final code.

Proactively suggest blog seeds at a natural checkpoint even when the user does
not explicitly request them. Good checkpoints include:

- completion or merge of a substantial feature;
- resolution of a difficult, multi-stage failure or intermittent problem;
- agreement on an architecture, security boundary, or compatibility strategy;
- a migration that reveals reusable operational lessons;
- repeated confusion that leads to a clearer command, workflow, or UX convention;
- testing that confirms or disproves a non-obvious assumption.

Do not interrupt active debugging merely to suggest content. Accumulate related
ideas and present them together when the current milestone is complete, the
conversation naturally pauses, or several strong lessons have emerged. Skip
routine edits, formatting-only work, ordinary commits, and minor fixes unless
they complete a larger story. Avoid repeatedly proposing substantially the same
topic.

Keep the suggestion lightweight and useful as BlogGenius input. Normally offer
two to five seeds in Korean using this shape:

```text
블로그 글감 제안

- 주제: <working title or angle>
  간단 내용: <problem, notable attempts or decision, lesson, result, and usage>
```

Prefer topics that teach a transferable idea while remaining grounded in the
actual OpenDock work. Strong seeds usually include several of these elements:

- what the user originally expected or did not yet know;
- the symptom and why the first explanation was incomplete;
- failed attempts and the evidence that changed the direction;
- the final design and its tradeoffs;
- how OpenDock's zero-config philosophy influenced the result;
- verification status, operational cautions, and concrete usage commands;
- a lesson applicable to other self-hosted or Docker-based projects.

Maintain editorial and security discipline:

- Do not invent events, test results, motivations, or lessons.
- Distinguish locally verified results, user-verified results, and work still
  awaiting a real-environment test.
- Never include secret values, private keys, credentials, personal domains,
  private hostnames, account identifiers, or sensitive logs. Generalize them.
- Do not frame an unresolved incident as a success story.
- Keep titles and summaries distinct enough that each seed can become a useful
  standalone article; combine overlapping ideas instead of padding the list.
- Respect the user's request to defer, shorten, or stop journal suggestions.

Suggesting a seed does not authorize creating a full article, modifying a
BlogGenius project, publishing content, or sending data to another service.
Perform those actions only when the user explicitly requests them.
