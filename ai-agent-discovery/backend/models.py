from dataclasses import asdict, dataclass, fields


@dataclass
class Agent:
    name: str
    description: str
    category: str
    tech_stack: list[str]
    github_stars: int | None = 0
    url: str | None = ""
    use_case: str | None = ""
    # "active" (or absent), "archived" or "dormant". A directory that does not
    # say a project has been archived is misleading in the one way that
    # matters when choosing a tool.
    status: str | None = "active"
    # Live entries to go to instead, for a project that has been archived. A
    # badge tells a reader to stop; it does not tell them where to go, and a
    # dead project with fifty thousand stars is still what they searched for.
    #
    # A field rather than a clause appended to the description, which is what
    # this replaced: the description is embedded, so naming two competitors in
    # it put them in the dead project's own vector, and the guard that
    # enforced the practice had to parse prose for a literal marker.
    alternatives: list[str] | None = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict) -> "Agent":
        """Build an Agent from a JSON record, ignoring unknown keys.

        agents.json is meant to be hand-edited, so extra fields should not
        break loading.
        """
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in record.items() if k in known})

    @property
    def metadata(self):
        """Returns metadata for vector store"""
        return {
            "name": self.name,
            "category": self.category,
            "stars": self.github_stars,
            "stack": ",".join(self.tech_stack),
            "description": self.description,
            "url": self.url,
            # Only when it is not the default: metadata is stored per document
            # in the index, and "active" on 223 records earns nothing.
            **({"status": self.status} if self.status and self.status != "active" else {}),
            # Carried so a card can render it beside the badge without a
            # second request. Comma-joined like `stack`, because FAISS
            # metadata values have to be scalars.
            **({"alternatives": ",".join(self.alternatives)} if self.alternatives else {}),
        }

    @property
    def page_content(self):
        """Returns text content for embedding.

        `alternatives` is deliberately absent. Naming a live competitor in
        text that gets embedded pulls the dead entry toward that competitor's
        queries, which is the opposite of what listing it is for.
        """
        return (
            f"Name: {self.name}\n"
            f"Description: {self.description}\n"
            f"Category: {self.category}\n"
            f"Tech Stack: {', '.join(self.tech_stack)}\n"
            f"Use Case: {self.use_case}"
        )
