from models import Agent


def test_from_dict_ignores_unknown_keys():
    agent = Agent.from_dict({
        "name": "Demo",
        "description": "d",
        "category": "c",
        "tech_stack": ["X"],
        "scraped_at": "2026-01-01",  # not a dataclass field
    })
    assert agent.name == "Demo"
    assert agent.github_stars == 0


def test_metadata_flattens_tech_stack_for_the_vector_store():
    agent = Agent("Demo", "d", "Cat", ["A", "B"], 5, "https://x", "use")
    assert agent.metadata["stack"] == "A,B"
    assert agent.metadata["stars"] == 5
    assert agent.metadata["category"] == "Cat"


def test_page_content_includes_the_searchable_fields():
    agent = Agent("Demo", "Does things", "Cat", ["A"], 5, "https://x", "automation")
    content = agent.page_content
    for expected in ("Demo", "Does things", "Cat", "A", "automation"):
        assert expected in content


def test_to_dict_round_trips_through_from_dict():
    agent = Agent("Demo", "d", "Cat", ["A", "B"], 5, "https://x", "use")
    assert Agent.from_dict(agent.to_dict()) == agent
