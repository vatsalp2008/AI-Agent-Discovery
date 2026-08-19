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

All three were replaced with narrower forms. The same applies to the
configuration filter: `prompt` alone would reject Prompt Optimizer, and
`skills` alone would reject a robotics skill library, so it matches
`system prompt`, `agent skill` and `plugin marketplace` instead.

The one thing it will not do is report success having checked nothing. If every
topic fails — no network, expired token, GitHub down — it exits non-zero and
says so. "Nothing new found" and "nothing was looked at" are opposite outcomes,
and on a schedule the second one silently looks like a healthy catalogue.

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

None of this argues against growing the catalogue. It argues for knowing
which categories are crowded before choosing where to grow, which is what the
report is for: yesterday's additions went into categories that were thin *and*
scoring well, and skipped Research and Infrastructure, the two weakest.
