from typing import List
from models import Agent
from vectorstore import VectorStore
import json
import os

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
        category="Task Automation",
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

def seed_data():
    """Seeds the database with sample agents."""
    print("Seeding data...")
    vs = VectorStore()
    
    # Check if data exists? For now, we just upsert.
    vs.add_agents(SAMPLE_AGENTS)
    
    # Also save to JSON for backup/reference
    agents_dict = [agent.to_dict() for agent in SAMPLE_AGENTS]
    os.makedirs('../data', exist_ok=True)
    with open('../data/agents.json', 'w') as f:
        json.dump(agents_dict, f, indent=2)
    
    print("Seeding complete.")

if __name__ == "__main__":
    seed_data()
