# Keeping the catalogue current

The catalogue is hand-curated. That is why it is any good — somebody chose
every entry — and why it needs maintenance: links rot, star counts drift, and
nobody notices a tool that launched last month.

Three jobs cover those three failure modes. All of them report; none of them
edits the catalogue without a person, except the star refresh, whose numbers
come from an authoritative API and whose audit trail is git history.

- [Links and stars](#-keeping-the-catalogue-honest)
- [Finding new agents](#-finding-new-agents)

## 🔗 Keeping the catalogue honest

```bash
make check-links      # verify every URL still resolves
make refresh-stars    # update star counts from the GitHub API
```

A `429` is reported as **throttled** rather than broken: it means the host
refused to answer, not that the page is gone. devin.ai returns one to every
automated request, so counting it as broken would fail the weekly job every
week for a page that works perfectly in a browser.

Projects get renamed, archived and deleted, and a dead link is invisible until
somebody clicks it. The checker distinguishes the two cases that matter: a
**broken** link needs fixing, while a **redirect** usually means the project
moved and the entry could be updated.

Both run weekly in a scheduled workflow, which commits refreshed star counts
directly and **fails on a broken link** — a summary nobody reads is not a
signal. Redirects are reported but tolerated, since the link still works, and
the check runs twice before failing so one flaky host does not turn the job red.

Renames are worth acting on: following them caught that Windsurf now ships as
Devin Desktop, which had left that entry stale in name, description and URL.

## Auditing what is already here

```bash
make audit                                          # report
python ai-agent-discovery/audit.py --apply-status   # write it back
python ai-agent-discovery/audit.py --stale-months 24
```

Finding new agents is half the job. The other half is entries that are already
here and no longer describe reality — and a curated catalogue rots quietly,
because nothing shows up until somebody clicks through.

| Reported | Meaning |
| --- | --- |
| `archived` | The repository is archived on GitHub |
| `dormant` | No commits for `--stale-months` (default 18) |
| `moved` | The org or repo was renamed; the API answers on the old path, so this is where the new name appears without following a redirect |
| `missing` | Deleted or made private |
| `stack` | The primary language is absent from the entry's `tech_stack` |

`archived` and `dormant` become a `status` on the entry, shown as a badge.
`moved` is followed automatically by `--follow-moves`, which rewrites only the
`owner/name` part of the URL — a link pointing at a subpath keeps it, and an
entry hosted outside GitHub is left alone. `missing` always wants a human: it
might mean the entry should go entirely.

Both writers refuse if any repository could not be checked, for the same
reason: an unchecked entry looks unflagged, and acting on that would clear a
warning nobody re-verified.

Two rules keep the report worth reading. **Format languages are not stack
findings** — GitHub reports whichever language has the most bytes, so an ML
project ships as "Jupyter Notebook"; ten of the first eighteen stack findings
were that, against entries correctly saying Python and PyTorch. And
`--apply-status` **refuses to write if anything could not be checked**, because
an unchecked entry looks unflagged and would have a real warning silently
cleared.

Statuses are cleared as well as set: archived repositories get unarchived, and
a stale warning is wrong in the other direction.

### What happens to a dead project

Archived entries stay. A project with fifty thousand stars is still what
people search for, and removing it means they find nothing and assume the
catalogue is thin rather than the project finished.

What they get instead is the badge **and a way forward**: an `alternatives`
field naming live entries already in the catalogue, rendered as links under
the badge. Flowise points at Langflow and Dify, Vanna AI at WrenAI, Chat2DB
and DB-GPT, Rebuff at AgentDojo and PurpleLlama.

It is a field rather than a sentence appended to the description, which is
what it replaced. The description is embedded, so naming two live competitors
in it put them inside the dead project's own vector — the opposite of what
listing them is for — and the guard enforcing the practice had to parse prose
for a literal marker that was documented nowhere but inside the assertion.
`alternatives` is deliberately absent from `page_content`.

Three rules, all enforced by `validate()`: only an archived entry may carry
it, every name must already be in the catalogue, and at most five — more than
a few is a reading list rather than a redirection. A public submission may not
set it at all, for the same reason it may not set `status`: "use my thing
instead" is exactly what a review queue exists to filter.

Dormant entries are left alone. Quiet is not dead: Bark and LLaVA have not
been touched in two years and are still perfectly usable, and 18 months of
silence is a prompt to check rather than a verdict.

### A failed audit is not a clean one

The weekly step keeps the audit's exit status rather than discarding it. It
used to run `audit.py … || true` and fall back to an empty `[]`, which meant
an expired token or a network outage produced exactly the output of a healthy
catalogue: the summary said "Every entry looks current" and the digest said
"Nothing outstanding". A run that could not check anything must not report
that it found nothing wrong, so a failure now prints a warning annotation and
says so in the summary — while still exiting 0, because the link check after
it is worth running either way.

### What the audit found

Run against 242 entries: **9 archived** and **10 dormant**, plus 8 whose
recorded `tech_stack` no longer matched the repository. Two of those had
drifted completely — OpenInterpreter is now 96% Rust after a rewrite while the
entry still said Python, and Quivr is 99.3% Python while the entry said
TypeScript. Neither would have surfaced without checking.

A `stack` finding is a prompt, not a verdict: the fix is a judgement about what
the entry should say, taken from the repository's own language breakdown rather
than from the single word GitHub reports as "the language".

### Rebuild it *after* the commit

`changelog.py` reads git history, so it can only see commits that already
exist. Running it in the same step as a catalogue edit produces a history that
is one commit behind — it describes the state before the change it was run for.

The weekly workflow gets this right by making the rebuild its own commit after
the data commits. Do the same by hand:

```bash
git commit -m "Add six agents"     # first
make changelog && git commit -am "Rebuild the change history"
```

## The weekly digest

```bash
make digest                                              # last 7 days
python ai-agent-discovery/digest.py --days 30 --audit audit.json
```

Four scheduled steps each wrote their own step summary and two of them opened
issues. That is four places to look and two to ignore. `digest.py` reads what
those steps already produced — `data/changelog.json` for what changed, and the
audit's JSON for what still needs a person — and turns it into one report.

It makes no network calls of its own, so it costs no API budget and can be run
offline. The weekly job passes it the audit findings and the crawler's
candidates, both produced earlier in the same run — so one schedule produces
one report covering what changed, what needs a decision and what could be
added. Discovery used to open its own issue every Thursday; a second weekly
issue is a second thing to read and the first thing to ignore.

Two rules keep it worth reading. Long lists are **abbreviated** past twelve
names: a busy week added 115 agents, and printing all of them is the wall the
digest exists to replace. And the weekly job **opens no issue for a quiet
week** — an issue saying "nothing changed" trains everyone to close it unread,
so a quiet week goes to the step summary and nowhere else.

The "needs a decision" section deliberately excludes `archived` and `dormant`:
the audit already acts on those by writing a status, and listing them would be
a to-do item nobody has to do.

## 🔭 Finding new agents

```bash
make discover                                   # what is missing, without queueing it
python ai-agent-discovery/discover.py           # queue the candidates for review
python ai-agent-discovery/discover.py --json    # for scripting; implies --dry-run
```

A hand-curated catalogue is good precisely because somebody chose every entry,
and stale for the same reason: nobody notices a tool that launched last month.
`discover.py` searches GitHub for the topics the catalogue already covers and
proposes what is genuinely new.

It writes nothing to the catalogue. Candidates go through the same
`submissions.submit()` a member of the public would use, so a maintainer still
approves each one by hand — which is what makes it safe to run unattended.

Most of the work is refusal, because a stars-sorted topic search is mostly
noise:

| Skipped | Why |
| --- | --- |
| Reading lists, guides, courses | `awesome-llm-apps` outranks every real tool by an order of magnitude, and no reviewer would ever accept one |
| Prompt dumps, skill packs, plugin marketplaces | Configuration *for* other agents, not software in its own right — the catalogue would list somebody's Claude Code settings next to Ollama |
| Taglines under 60 characters | The description is what gets embedded, so it has to say what the tool *does* |
| Anything it cannot categorise | A wrong category teaches the catalogue's own structure something false, so no proposal is better |
| RPA tools tagged `robotics` | EasySpider and Wechaty both are, and neither is robotics |
| Repos already known | Matched on `owner/name`, so a trailing slash is not a new project — and the pending queue counts, or every run re-proposes what the reviewer has not got to |
| Archived repositories | `archived:false` in the query. A repository can be archived *and* recently pushed, so the date filter below does not imply this one: microsoft/TaskWeaver was archived at 6,176 stars with a push inside any six-month window |
| Anything quiet for six months | `pushed:>=` a date `DEFAULT_FRESH_MONTHS` back. Shorter than audit.py's 18-month dormancy line on purpose — that asks whether an entry already vetted has gone quiet, this asks whether a stranger is worth a reviewer's attention at all |

Both are query filters rather than checks on the results, so a dead project
never occupies one of the per-topic slots a live one could have used. The
freshness window applies to a bare `make discover` too. It did not always: the
default was "no filter", and one hand-run session produced six candidates —
Petals, TaskWeaver, Voyager, AgentVerse, bolt.new and uptrain — that were all
archived or two years silent, each rejected by hand after being looked up.

Discovery is run by hand; the weekly job runs the crawler only to fold its
findings into the digest, and opens no issue of its own. It reports rather
than queues because `data/submissions.jsonl` is runtime state and gitignored,
so a queue written on an ephemeral runner would vanish with it.

### What the filter actually does

Measured by running it over five live topic searches — `ai-agents`, `llm`,
`rag`, `agents`, `llmops`, 150 results — rather than reasoning about it:

| Outcome | Count |
| --- | ---: |
| Already in the catalogue | 73 |
| Usable, proposed to a reviewer | 34 |
| Refused as not a tool | 22 |
| Description under 60 characters | 17 |
| No category matched | 3 |
| No technologies found | 1 |

Two things came out of that. Every one of the 22 refusals was correct — guides,
awesome-lists, leaked prompt collections, skill packs — so the phrase list is
not over-reaching. And the categoriser, which looked like the bottleneck, is
responsible for three drops; the 60-character floor accounts for six times as
many, and it is doing its job on taglines like "The agent that grows with you",
which says nothing that could be embedded.

A run now names its near misses by reason instead of reporting "25 unusable".
"Not a tool" is excluded from that list — the filter working is not a near
miss — and the tool check runs before the length check so a course with a
six-word tagline is reported as a course rather than as something to go and
lengthen.

**Topics are read as well as prose.** A repository that is teaching rather
than shipping usually tags itself, and that survives translation where a
phrase list does not: 从零开始构建智能体 was never going to match an English
phrase, but it still carries `tutorial`.

### Staying inside the API budget

GitHub's search endpoint allows **10 requests a minute unauthenticated** and 30
with a token — far tighter than the 60/hour that applies to the rest of the
API. The crawler paces itself accordingly: 6.5 seconds between topics without a
token, 2.0 with one. Set `GITHUB_TOKEN` and a full sixteen-topic run finishes in
about thirty seconds instead of two minutes.

If it is rate limited anyway, it **stops and keeps what it has** rather than
failing the run. The searches already made cost real budget, and discarding
their results means the next run spends that budget again to learn the same
thing.

### Why the refusal phrases are narrow

Every phrase is checked against the catalogue itself: a maintainer accepted
each entry, so an entry is a tool by definition, and a phrase that rejects one
is too broad. Three were caught that way and read as obviously correct in a
list:

| Phrase | Rejected | Because |
| --- | --- | --- |
| `collection of` | MCP Servers | "the reference **collection of** Model Context Protocol servers" |
| `paper` | PaperQA | "questions over scientific **papers** with citations" |
| `boilerplate` | Jina Reader | "stripping navigation and **boilerplate**" |
| `example` | ChatterBot | "learns replies from **example** conversations" |
| `interview` | STORM | "by simulating expert **interviews**" |
| `course` | Agentic Radar | "where a prompt could take it **off course**" |

All six were replaced with narrower forms.

**`course` took three attempts**, and each failure was the opposite of the
last: the bare word refused an agent security scanner, enumerating eight
phrases let huggingface/agents-course and mlcourse.ai through, and a pair of
lookbehinds then refused "off-course", "over the course of", "course
correction" and "obstacle course". What separates them is not the word but
where it sits — a repository that *is* a course says so in its name, and in
prose the genre carries an article or a learning word that the idioms never
have. `COURSE_NAME_PATTERN` reads the name, `COURSE_TEXT_PATTERN` the
description, and one test table checks seventeen cases in both directions,
because every earlier version passed its own tests.

**`interview` does not live in the phrase list at all.** It is the one word
where narrowing to phrases was not enough, and the record of getting it wrong
is worth keeping. `interview prep` cannot match "interview preparation", and
the pattern's trailing `s?` only pluralises the end of a phrase, so
`interview questions` left the singular free. The replacement — matching
`interview` near any of *prep, question, answer, guide, handbook, cheat*, plus
a bare "technical / job / system design interview" — then refused an agent
that "conducts technical interviews with candidates", one that "automates job
interviews", and one that "runs customer interviews and turns the answers into
a report". AI interviewers are a real and growing category, and the crawler
was dropping every one of them silently.

`INTERVIEW_PREP_PATTERN` in `discover.py` matches only the phrasings that
never mean anything else — interview prep, interview practice, preparing for
an interview. Two phrases sit apart in `INTERVIEW_QUESTIONS_PATTERN`, where a
verb can override them: an AI recruiter *generates* interview questions and
*conducts* mock interviews, and refusing every one of those costs a category
nobody ever sees. "Run mock interviews and grade yourself" gets past as a
result — one rejection by a reviewer against a whole category never reaching
one. "System design interviews explained" gets
past it, and that is deliberate — catching it needs the bare-phrase branch
that caused the false positives, and one prep repository reaching a reviewer
is cheaper than a category that never reaches one. The same applies to the
configuration filter: `prompt` alone would reject Prompt Optimizer, and
`skills` alone would reject a robotics skill library, so it matches
`system prompt`, `agent skill` and `plugin marketplace` instead.

The one thing it will not do is report success having checked nothing. If every
topic fails — no network, expired token, GitHub down — it exits non-zero and
says so. "Nothing new found" and "nothing was looked at" are opposite outcomes,
and on a schedule the second one silently looks like a healthy catalogue.

### The bootstrap copy drifts

`SAMPLE_AGENTS` in `scraper.py` seeds a checkout that has no
`data/agents.json`. Nothing else reads it, so it drifts silently and only
someone starting fresh ever sees the result — which is the worst audience to
show a stale answer to.

It had drifted twenty-two fields deep before anyone looked: Cursor and Aider
pointed at URLs that had moved, OpenInterpreter still claimed Python and GPT-4
after the Rust rewrite, one entry kept a name the catalogue had changed, and
fourteen carried no health status at all — so four entries whose descriptions
read "archived, with X maintained" would have rendered with no badge and been
served under `maintained=true`.

`test_the_bootstrap_copy_agrees_with_the_catalogue` compares every shared
entry on description, category, url, use case, stack and status. The set is
deliberately smaller than the catalogue — it exists to make an empty checkout
usable, not to mirror every addition — so only entries present in both are
checked.

## Is the catalogue still findable?

```bash
make quality                                        # the report
python ai-agent-discovery/quality.py --category Research
python ai-agent-discovery/quality.py --json > quality.json
```

Links rot and stars drift, and both are easy to check. Retrieval quality
decays too, and nothing announced it: every agent added is another neighbour
competing for the same queries, and the loss shows up one displaced result at
a time.

`quality.py` puts two numbers on it.

**Self-retrieval.** Ask for each agent using its own `use_case` and see where
it ranks, averaged per category as a mean reciprocal rank. An entry its own
description cannot find is, in practice, not in the catalogue. This is how
TransformerLens surfaced: it sat outside the top ten for "Understanding what a
model has learned", a use case that equally describes half the catalogue.
Rewritten to "Mechanistic interpretability research" — the term people
actually search — it returns first.

**Guard margin.** For each case in the live retrieval suite, the gap between
the best expected result and the best result that would fail it. This exists
because a guard can be green and worthless at the same time:
`fine tune a model on one GPU` passed for weeks with its expected agent third
by **0.002**, while two entries that answer a different question outranked
every right one. The next agent added displaced it, which read as a regression
in that change rather than a weakness that had been there all along.

**Movement.** `make quality-record` appends the run to
`data/quality-history.jsonl`, and every later report says which categories
moved since, in both directions. A single run cannot tell decay from a
deliberate trade: fine-tuning dropped 0.972 → 0.957 the day Unsloth and PEFT
were reworded, and without the record beside it that number is just a lower
number. Recording is a deliberate step rather than something CI does, because
CI runs on every push and cannot commit, so a line written there would go in
the bin with the runner.

Only whole-catalogue runs are recorded — `--category` measures a subset, and
comparing that against a full run reports the difference between two
questions as a change over time.

**Published, not private.** `/api/quality` serves the recorded runs and
`/changes` renders them: the weakest category, every score as a bar, and what
moved since the previous measurement. A directory that has grown past the
point of being searchable should say so where people can see it. The panel
loads independently of the change history on that page, so neither can take
the other down — the history is the reason to visit, and it should not vanish
because nobody has measured lately.

Nothing here fails a build. The scores are a property of the catalogue and of
the embedding model, and the signal is how they move between runs, not whether
they clear some absolute bar. Two findings on the first run were worth acting
on, though:

| Found | Done |
| --- | --- |
| `transcribe speech to text` returned two **text-to-speech** tools above every speech-to-text one, and passed by 0.0067 | Five entries said "speech recognition"; embeddings do not read direction, and "speech-to-text" is both the commoner term and the unambiguous one. Whisper went from sixth (0.6396) to first (0.7372) |
| `automated machine learning on tabular data` expected only AutoGluon and SDV | H2O-3 takes first place and is equally an answer, as are PyCaret and FLAML. The guard was narrower than the question |
| TransformerLens and MetaGPT sat outside the top ten for their own use case | Both said nothing specific — "Understanding what a model has learned", and a README tagline about returning a "PRD". Reworded; no entry is outside the top ten now |

### What it costs to grow

The report is most useful pointed at the thing that caused it. Twenty-five
agents went in over one day (278 → 303), and the scores moved in both
directions.

Only three categories grew *without* also having an entry reworded, so only
these three isolate the cost of adding alone:

| Category | Before | After | Added |
| --- | ---: | ---: | ---: |
| MLOps | 0.967 | 0.975 | 5 |
| Customer Service | 0.967 | 0.947 | 4 |
| Safety | 0.921 | 0.849 | 2 |

Five well-differentiated deployment tools *raised* MLOps. Two red-teaming
tools cost safety seven points, because they landed on top of Garak, PyRIT
and Rebuff, which already answer the same question. Adding to a crowded
category is not free, and the bill is paid by every entry already in it.

Automation (+7), Fine-tuning (+5), Evaluation (+2), Multimodal and Autonomous
Agent all had wording changed in the same day, so their movement cannot be
attributed to the additions and is left out rather than guessed at.

One of those is worth its own note. Fine-tuning fell from 0.972 to **0.957**
after Unsloth and PEFT were reworded around "one GPU" — the change that fixed
`fine tune a model on one GPU`, which had been thin for a week. Aiming an
entry at the question people ask moved it away from the question this metric
asks, which is its own `use_case`. That is a real trade and worth making;
it is recorded here so the drop is not later read as decay.

### The use case is the half that gets asked

The report queries each entry's `use_case`, and the single most common cause
of a weak score turned out to be a use case that names the *category* rather
than the tool. Safety had four entries whose use case was some arrangement of
"red teaming" and two that both said "model robustness"; every one of those
tools is distinct, and every one of the descriptions said so. Only the use
cases had collapsed into each other.

Rewriting fifteen of them — to agree with the description already present,
changing no facts — moved eight categories at once:

| Category | Before | After |
| --- | ---: | ---: |
| Safety | 0.849 | 0.976 |
| Multimodal | 0.889 | 0.957 |
| Evaluation | 0.917 | 0.976 |
| Framework | 0.895 | 0.952 |
| Autonomous Agent | 0.895 | 0.944 |
| Research | 0.879 | 0.917 |
| Infrastructure | 0.894 | 0.924 |
| Data Analysis | 0.968 | 1.000 |

`test_no_two_entries_share_a_use_case` now refuses an exact collision. Only
exact ones: twenty-three fine-tuning tools all mention fine-tuning, and that
is honest rather than lazy — the difference needs judgement, which is what
the report is for.

What did *not* respond to rewriting is worth naming too. Apache Airflow still
loses "Scheduling data and ML pipelines" to Mage, and PrivateGPT still loses
to AnythingLLM and LocalGPT. Those are not vague entries; they are tools that
genuinely do the same job, and rewording one to escape the other would be
tuning the catalogue to flatter a metric.

None of this argues against growing the catalogue. It argues for knowing
which categories are crowded before choosing where to grow, which is what the
report is for: yesterday's additions went into categories that were thin *and*
scoring well, and skipped Research and Infrastructure, the two weakest.
