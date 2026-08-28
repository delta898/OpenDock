# OpenDock Agent Guidance

## Development journal and BlogGenius seeds

OpenDock is developed together with the user, who may turn meaningful parts of
that work into articles with BlogGenius. Treat the reasoning, failed attempts,
tradeoffs, operational lessons, and user-facing outcomes as potential material,
not only the final code.

The durable backlog for these ideas is `docs/blog-seeds.md`. Read that file
before proposing or recording a seed. At a natural checkpoint, update an
existing entry with better evidence or add a new entry when the subject is
distinct and substantial. The conversation suggestion is a short notification;
the document is the detailed source of truth. Mention material backlog changes
to the user, but do not turn every minor update into a blog suggestion.

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

Entries in `docs/blog-seeds.md` should be detailed enough to prevent a generic
article. For each seed, record:

- a working topic and the specific reader question or angle;
- the OpenDock-specific context, symptoms, attempts, decisions, and tradeoffs;
- evidence such as related commits, files, commands, or generalized log clues;
- what was verified locally, what the user verified in a real environment, and
  what remains unverified;
- concrete lessons and cautions that BlogGenius should preserve.

Focus detail on our distinctive experience and reasoning. Do not spend many
lines restating general Docker, Git, reverse-proxy, or Supabase background that
BlogGenius can supply. Merge overlapping entries instead of creating several
thin variations. Use backlog states `seed`, `ready`, `drafted`, and `published`;
do not advance an entry beyond `seed` without the user's direction. When an
article is drafted or published, preserve the seed and add its status and link
instead of deleting the historical material.

Maintain editorial and security discipline:

- Do not invent events, test results, motivations, or lessons.
- Distinguish locally verified results, user-verified results, and work still
  awaiting a real-environment test.
- Never include secret values, private keys, credentials, personal domains,
  private hostnames, account identifiers, or sensitive logs. Generalize them.
- Do not frame an unresolved incident as a success story.
- Keep titles and summaries distinct enough that each seed can become a useful
  standalone article; combine overlapping ideas instead of padding the list.
- Treat commit messages as evidence pointers, not as complete history. Inspect
  the relevant diff and documentation before recording detailed claims.
- Respect the user's request to defer, shorten, or stop journal suggestions.

Suggesting a seed does not authorize creating a full article, modifying a
BlogGenius project, publishing content, or sending data to another service.
Perform those actions only when the user explicitly requests them.
