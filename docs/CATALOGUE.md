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
| Taglines under 60 characters | The description is what gets embedded, so it has to say what the tool *does* |
| Anything it cannot categorise | A wrong category teaches the catalogue's own structure something false, so no proposal is better |
| RPA tools tagged `robotics` | EasySpider and Wechaty both are, and neither is robotics |
| Repos already known | Matched on `owner/name`, so a trailing slash is not a new project — and the pending queue counts, or every run re-proposes what the reviewer has not got to |

A weekly workflow runs it and **opens an issue** listing what it found, rather
than queueing: `data/submissions.jsonl` is runtime state and gitignored, so a
queue written on an ephemeral runner would vanish with it. Nothing new is the
usual result, and no issue is opened in that case.

Set `GITHUB_TOKEN` to raise the API limit from 60/hour; search is capped
tighter still, so the crawler paces itself between topics.
