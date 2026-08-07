import json
import logging
import os

import config
from models import Agent
from vectorstore import VectorStore

logger = logging.getLogger(__name__)

SAMPLE_AGENTS = [
    # Code Generation
    Agent(
        name="Cursor",
        description="An AI-powered code editor built on VS Code that lets you write, edit, and chat with your code.",
        category="Code Generation",
        tech_stack=["Electron", "GPT-4", "VS Code"],
        github_stars=35000,
        url="https://cursor.sh",
        use_case="Code editing, refactoring, generation"
    ),
    Agent(
        name="Aider",
        description="A command line tool that lets you pair program with GPT-3.5/4. Edits code in your local git repo.",
        category="Code Generation",
        tech_stack=["Python", "GPT-4", "Git"],
        github_stars=12000,
        url="https://github.com/paul-gauthier/aider",
        use_case="Terminal-based pair programming"
    ),
    Agent(
        name="GitHub Copilot",
        description="Your AI pair programmer. Uses OpenAI Codex to suggest code and entire functions in real-time.",
        category="Code Generation",
        tech_stack=["TypeScript", "OpenAI Codex"],
        github_stars=0, # Proprietary, likely huge
        url="https://github.com/features/copilot",
        use_case="Code completion, suggestions"
    ),
     Agent(
        name="OpenInterpreter",
        description="A natural language interface for computers. Lets LLMs run code (Python, Javascript, Shell) locally.",
        category="Code Generation",
        tech_stack=["Python", "Llama 2", "GPT-4"],
        github_stars=45000,
        url="https://github.com/OpenInterpreter/open-interpreter",
        use_case="Local system control, script execution"
    ),

    # Research & Autonomous
    Agent(
        name="AutoGPT",
        description="An experimental open-source attempt to make GPT-4 fully autonomous.",
        category="Autonomous Agent",
        tech_stack=["Python", "GPT-4", "Pinecone"],
        github_stars=160000,
        url="https://github.com/Significant-Gravitas/Auto-GPT",
        use_case="Goal-oriented autonomous tasks"
    ),
    Agent(
        name="GPT Researcher",
        description="GPT Researcher is an autonomous agent designed for comprehensive online research on any given task.",
        category="Research",
        tech_stack=["Python", "LangChain", "Selenium"],
        github_stars=14000,
        url="https://github.com/assafelovic/gpt-researcher",
        use_case="Deep web research, report generation"
    ),
    Agent(
        name="BabyAGI",
        description="A framework for managing tasks using AI. It creates tasks based on the result of previous tasks.",
        category="Autonomous Agent",
        tech_stack=["Python", "OpenAI API", "Pinecone"],
        github_stars=19000,
        url="https://github.com/yoheinakajima/babyagi",
        use_case="Task management, loop execution"
    ),

    # Data Analysis
    Agent(
        name="PandasAI",
        description="A Python library that integrates generative artificial intelligence capabilities into pandas, making dataframes conversational.",
        category="Data Analysis",
        tech_stack=["Python", "Pandas", "LLMs"],
        github_stars=11000,
        url="https://github.com/gventuri/pandas-ai",
        use_case="Chat with data, analysis"
    ),
    Agent(
        name="Vanna AI",
        description="Retrieval-augmented text-to-SQL: ask questions in plain English and get SQL that runs against your warehouse.",
        category="Data Analysis",
        tech_stack=["Python", "RAG", "SQL"],
        github_stars=19000,
        url="https://github.com/vanna-ai/vanna",
        use_case="Natural language querying of databases"
    ),
    Agent(
        name="Jupyter AI",
        description="Brings generative AI into JupyterLab with a chat panel and %%ai magics that work against any notebook cell.",
        category="Data Analysis",
        tech_stack=["Python", "JupyterLab"],
        github_stars=3500,
        url="https://github.com/jupyterlab/jupyter-ai",
        use_case="AI assistance inside notebooks"
    ),
    Agent(
        name="LIDA",
        description="Generates visualisations and infographics from data using LLMs, including the grammar-agnostic chart code.",
        category="Data Analysis",
        tech_stack=["Python", "Altair", "Matplotlib"],
        github_stars=2800,
        url="https://github.com/microsoft/lida",
        use_case="Automatic chart and infographic generation"
    ),
    Agent(
        name="Sketch",
        description="An AI coding assistant for pandas that understands the contents of a dataframe, not just its schema.",
        category="Data Analysis",
        tech_stack=["Python", "Pandas"],
        github_stars=2300,
        url="https://github.com/approximatelabs/sketch",
        use_case="Dataframe-aware code suggestions"
    ),
    Agent(
        name="DB-GPT",
        description="A private data application framework that puts an agent layer over databases and warehouses.",
        category="Data Analysis",
        tech_stack=["Python", "Local LLM", "SQL"],
        github_stars=16000,
        url="https://github.com/eosphoros-ai/DB-GPT",
        use_case="Private database question answering"
    ),
    Agent(
        name="Windsurf",
        description="An agentic IDE from Codeium whose Cascade mode keeps context across a whole multi-file change.",
        category="Code Generation",
        tech_stack=["Electron", "TypeScript"],
        github_stars=0,
        url="https://codeium.com/windsurf",
        use_case="Agentic multi-file editing in an IDE"
    ),
    Agent(
        name="Zed",
        description="A high-performance collaborative editor written in Rust, with inline AI assistance and multibuffer edits.",
        category="Code Generation",
        tech_stack=["Rust", "GPUI"],
        github_stars=58000,
        url="https://github.com/zed-industries/zed",
        use_case="Fast native editing with AI assistance"
    ),
    Agent(
        name="Tabby",
        description="A self-hosted AI coding assistant that runs entirely on your own hardware, with no external calls.",
        category="Code Generation",
        tech_stack=["Rust", "Local LLM"],
        github_stars=24000,
        url="https://github.com/TabbyML/tabby",
        use_case="Self-hosted code completion"
    ),
    Agent(
        name="Devika",
        description="An open agentic engineer that takes a high-level instruction, researches it, and writes the code.",
        category="Code Generation",
        tech_stack=["Python", "Playwright"],
        github_stars=19000,
        url="https://github.com/stitionai/devika",
        use_case="Instruction-to-implementation coding"
    ),
    Agent(
        name="Plandex",
        description="A terminal agent for large tasks that keeps changes in a sandbox until you approve them.",
        category="Code Generation",
        tech_stack=["Go", "GPT-4"],
        github_stars=11000,
        url="https://github.com/plandex-ai/plandex",
        use_case="Reviewable multi-step terminal coding"
    ),
    Agent(
        name="CodeRabbit",
        description="An AI reviewer that comments on pull requests line by line and tracks whether feedback was addressed.",
        category="Code Generation",
        tech_stack=["TypeScript", "GitHub API"],
        github_stars=0,
        url="https://coderabbit.ai",
        use_case="Automated pull request review"
    ),
    Agent(
        name="MetaGPT",
        description="The Multi-Agent Framework: Given one line Requirement, return PRD, Design, Tasks, Repo.",
        category="Autonomous Agent",
        tech_stack=["Python", "Multi-Agent"],
        github_stars=38000,
        url="https://github.com/geekan/MetaGPT",
        use_case="Software development lifecycle automation"
    ),

    # Frameworks (acting as base for agents but often valid searches)
    Agent(
        name="LangChain",
        description="Building applications with LLMs through composability.",
        category="Framework",
        tech_stack=["Python", "TypeScript"],
        github_stars=85000,
        url="https://github.com/langchain-ai/langchain",
        use_case="LLM orchestration"
    ),
    Agent(
        name="CrewAI",
        description="Cutting-edge framework for orchestrating role-playing, autonomous AI agents.",
        category="Framework",
        tech_stack=["Python", "Agents"],
        github_stars=15000,
        url="https://github.com/joaomdmoura/crewAI",
        use_case="Multi-agent orchestration"
    ),

    # Customer Service / Chat
    Agent(
        name="Rasa",
        description="Open source machine learning framework for automated text and voice-based conversations.",
        category="Customer Service",
        tech_stack=["Python", "TensorFlow"],
        github_stars=18000,
        url="https://github.com/RasaHQ/rasa",
        use_case="Enterprise chatbots"
    ),
    Agent(
        name="Botpress",
        description="The building blocks for building chatbots. Visual flow editor.",
        category="Customer Service",
        tech_stack=["TypeScript", "Node.js"],
        github_stars=12000,
        url="https://botpress.com",
        use_case="Visual chatbot builder"
    ),

    # Automation
    Agent(
        name="Zapier AI Actions",
        description="Equip AI agents with the ability to run 20,000+ actions on Zapier.",
        category="Automation",
        tech_stack=["API", "SaaS"],
        github_stars=500,
        url="https://zapier.com/ai",
        use_case="Connecting AI to thousands of apps"
    ),
    Agent(
        name="n8n",
        description="Fair-code workflow automation tool. Easily automate tasks across different services.",
        category="Automation",
        tech_stack=["TypeScript", "Node.js"],
        github_stars=40000,
        url="https://n8n.io",
        use_case="Workflow automation"
    ),

     # More Agents to hit 20+
    Agent(
        name="SuperAGI",
        description="Open Source autonomous AI agent framework to develop and deploy useful autonomous agents.",
        category="Autonomous Agent",
        tech_stack=["Python", "Docker", "PostgreSQL"],
        github_stars=14500,
        url="https://github.com/TransformerOptimus/SuperAGI",
        use_case="Agent provisioning and management"
    ),
    Agent(
        name="ChatDev",
        description="Communicative Agents for Software Development. A virtual software company.",
        category="Code Generation",
        tech_stack=["Python", "Role-Playing"],
        github_stars=22000,
        url="https://github.com/OpenBMB/ChatDev",
        use_case="Full software project generation"
    ),
    Agent(
        name="PrivateGPT",
        description="Interact with your documents using the power of GPT, 100% privately, no data leaks.",
        category="Research",
        tech_stack=["Python", "LlamaIndex", "Local LLM"],
        github_stars=55000,
        url="https://github.com/imartinez/privateGPT",
        use_case="Document QA, RAG"
    ),
    Agent(
        name="Quivr",
        description="Your Second Brain, empowered by Generative AI.",
        category="Research",
        tech_stack=["TypeScript", "Supabase", "React"],
        github_stars=32000,
        url="https://github.com/StanGirard/quivr",
        use_case="Personal knowledge base"
    ),
    Agent(
        name="LocalGPT",
        description="Chat with your documents on your local device using GPT models. No data leaves your device.",
        category="Research",
        tech_stack=["Python", "LangChain", "ChromaDB"],
        github_stars=18000,
        url="https://github.com/PromtEngineer/localGPT",
        use_case="Local RAG"
    ),
    Agent(
        name="Sweep",
        description="Sweep is an AI junior developer that transforms bug reports and feature requests into code changes.",
        category="Code Generation",
        tech_stack=["Python", "GitHub API"],
        github_stars=7000,
        url="https://github.com/sweepai/sweep",
        use_case="Bug fixing, feature implementation"
    )
]

class CatalogueError(Exception):
    """agents.json exists but cannot be used."""


def _parse_records(raw: str) -> list:
    """Parse agents.json, naming the problem if it is malformed.

    The docs invite hand-editing this file, so a typo is an ordinary event and
    deserves a message that says where to look — not a raw JSONDecodeError.
    """
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CatalogueError(
            f"{config.AGENTS_JSON} is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})"
        ) from e

    if not isinstance(records, list):
        raise CatalogueError(
            f"{config.AGENTS_JSON} must contain a JSON array of agents, "
            f"found {type(records).__name__}."
        )
    return records


def _build_agent(record, index: int) -> Agent:
    """Turn one record into an Agent, reporting which entry is at fault."""
    where = f"entry {index} of {config.AGENTS_JSON}"
    if not isinstance(record, dict):
        raise CatalogueError(f"{where} must be an object, found {type(record).__name__}.")

    try:
        return Agent.from_dict(record)
    except TypeError as e:
        name = record.get("name")
        label = f"{where} ({name!r})" if name else where
        raise CatalogueError(f"{label} is not a valid agent: {e}") from e


def load_agents() -> list[Agent]:
    """Load the agent catalogue.

    data/agents.json is the source of truth once it exists, so hand-edits
    survive re-seeding. SAMPLE_AGENTS only bootstraps a fresh checkout.

    A catalogue that exists but is broken raises rather than falling back to
    the samples: silently indexing different data than the file says would be
    worse than stopping.
    """
    if os.path.exists(config.AGENTS_JSON):
        with open(config.AGENTS_JSON) as f:
            records = _parse_records(f.read())

        if records:
            agents = [_build_agent(record, i) for i, record in enumerate(records)]
            _warn_about_duplicates(agents)
            logger.info("Loaded %d agents from %s", len(agents), config.AGENTS_JSON)
            return agents
        logger.warning("%s is empty; using the built-in sample agents.", config.AGENTS_JSON)

    logger.info("Using %d built-in sample agents.", len(SAMPLE_AGENTS))
    return list(SAMPLE_AGENTS)


def _warn_about_duplicates(agents: list[Agent]) -> None:
    """Duplicate names index fine but make lookups by name ambiguous."""
    seen, duplicates = set(), set()
    for agent in agents:
        key = (agent.name or "").casefold()
        if key in seen:
            duplicates.add(agent.name)
        seen.add(key)
    if duplicates:
        logger.warning(
            "Duplicate agent names in %s: %s. Lookups by name return the first match.",
            config.AGENTS_JSON, ", ".join(sorted(duplicates)),
        )


def write_agents_json(agents: list[Agent]) -> None:
    """Persist the catalogue back to data/agents.json."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.AGENTS_JSON, 'w') as f:
        json.dump([agent.to_dict() for agent in agents], f, indent=2)
        # Trailing newline so re-seeding does not fight the end-of-file-fixer
        # pre-commit hook, which would otherwise flip the file back and forth.
        f.write("\n")


def seed_data(rebuild: bool = True):
    """Index the agent catalogue into the vector store.

    Rebuilds by default: `add_agents` appends, so re-running the seed script
    against an existing index would otherwise duplicate every agent.
    """
    logger.info("Seeding data...")
    agents = load_agents()
    vs = VectorStore()

    if rebuild:
        vs.replace_agents(agents)
    else:
        vs.add_agents(agents)

    write_agents_json(agents)
    logger.info("Seeding complete: %d agents indexed.", len(agents))

if __name__ == "__main__":
    import sys

    from logging_setup import configure

    configure()
    try:
        seed_data()
    except CatalogueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
