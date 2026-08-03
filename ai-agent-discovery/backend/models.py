from dataclasses import dataclass, asdict, fields
from typing import List, Optional

@dataclass
class Agent:
    name: str
    description: str
    category: str
    tech_stack: List[str]
    github_stars: Optional[int] = 0
    url: Optional[str] = ""
    use_case: Optional[str] = ""

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
            "url": self.url
        }

    @property
    def page_content(self):
        """Returns text content for embedding"""
        return f"Name: {self.name}\nDescription: {self.description}\nCategory: {self.category}\nTech Stack: {', '.join(self.tech_stack)}\nUse Case: {self.use_case}"
