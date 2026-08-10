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
        name="RAGFlow",
        description="A RAG engine built on deep document understanding, with layout-aware chunking and grounded citations.",
        category="Research",
        tech_stack=["Python", "Elasticsearch", "Docker"],
        github_stars=32000,
        url="https://github.com/infiniflow/ragflow",
        use_case="Document-grounded question answering"
    ),
    Agent(
        name="Verba",
        description="Weaviate's open RAG interface for importing documents and querying them with citations.",
        category="Research",
        tech_stack=["Python", "Weaviate", "React"],
        github_stars=7000,
        url="https://github.com/weaviate/Verba",
        use_case="Turnkey retrieval-augmented chat"
    ),
    Agent(
        name="Khoj",
        description="A self-hosted second brain that searches your notes, documents and the web from one place.",
        category="Research",
        tech_stack=["Python", "Django", "Local LLM"],
        github_stars=27000,
        url="https://github.com/khoj-ai/khoj",
        use_case="Personal knowledge search"
    ),
    Agent(
        name="Mem0",
        description="A memory layer that lets agents remember user preferences and facts across sessions.",
        category="Framework",
        tech_stack=["Python", "Vector DB"],
        github_stars=27000,
        url="https://github.com/mem0ai/mem0",
        use_case="Long-term memory for agents"
    ),
    Agent(
        name="Letta",
        description="Formerly MemGPT: agents with persistent memory that manage their own context window.",
        category="Framework",
        tech_stack=["Python", "PostgreSQL"],
        github_stars=17000,
        url="https://github.com/letta-ai/letta",
        use_case="Stateful agents with self-managed memory"
    ),
    Agent(
        name="Unstructured",
        description="Preprocessing pipelines that turn PDFs, HTML and images into clean chunks for retrieval.",
        category="Framework",
        tech_stack=["Python", "OCR"],
        github_stars=11000,
        url="https://github.com/Unstructured-IO/unstructured",
        use_case="Document ingestion for RAG"
    ),
    Agent(
        name="Skyvern",
        description="Automates browser workflows using vision models, so it survives layout changes that break selectors.",
        category="Automation",
        tech_stack=["Python", "Playwright", "Vision"],
        github_stars=22706,
        url="https://github.com/Skyvern-AI/skyvern",
        use_case="Resilient browser automation"
    ),
    Agent(
        name="Stagehand",
        description="An AI browser framework that mixes natural-language steps with ordinary Playwright code.",
        category="Automation",
        tech_stack=["TypeScript", "Playwright"],
        github_stars=23761,
        url="https://github.com/browserbase/stagehand",
        use_case="Hybrid scripted and AI browsing"
    ),
    Agent(
        name="Activepieces",
        description="An open source automation platform with AI steps and several hundred connectors.",
        category="Automation",
        tech_stack=["TypeScript", "Node.js"],
        github_stars=23616,
        url="https://github.com/activepieces/activepieces",
        use_case="Open source workflow automation"
    ),
    Agent(
        name="Vocode",
        description="A library for building real-time voice agents that can hold a phone conversation.",
        category="Customer Service",
        tech_stack=["Python", "Twilio", "Speech"],
        github_stars=3783,
        url="https://github.com/vocodedev/vocode-core",
        use_case="Voice agents and phone calls"
    ),
    Agent(
        name="Chatwoot",
        description="An open customer engagement suite with AI-assisted replies across chat, email and social.",
        category="Customer Service",
        tech_stack=["Ruby", "Vue.js"],
        github_stars=35586,
        url="https://github.com/chatwoot/chatwoot",
        use_case="Omnichannel customer support"
    ),
    Agent(
        name="K8sGPT",
        description="Scans a Kubernetes cluster, diagnoses problems and explains them in plain English.",
        category="Automation",
        tech_stack=["Go", "Kubernetes"],
        github_stars=8053,
        url="https://github.com/k8sgpt-ai/k8sgpt",
        use_case="Cluster diagnostics and triage"
    ),
    Agent(
        name="Langfuse",
        description="Open source LLM engineering platform: tracing, evaluation, prompt management and cost tracking.",
        category="Evaluation",
        tech_stack=["TypeScript", "PostgreSQL", "OpenTelemetry"],
        github_stars=32763,
        url="https://github.com/langfuse/langfuse",
        use_case="Tracing and evaluating LLM applications"
    ),
    Agent(
        name="Phoenix",
        description="Arize's open observability tool for tracing, evaluating and debugging LLM and RAG pipelines.",
        category="Evaluation",
        tech_stack=["Python", "OpenTelemetry"],
        github_stars=10955,
        url="https://github.com/Arize-ai/phoenix",
        use_case="Debugging retrieval and agent traces"
    ),
    Agent(
        name="DeepEval",
        description="A unit-testing framework for LLM outputs, with metrics for hallucination, relevance and bias.",
        category="Evaluation",
        tech_stack=["Python", "pytest"],
        github_stars=17484,
        url="https://github.com/confident-ai/deepeval",
        use_case="Regression testing LLM behaviour"
    ),
    Agent(
        name="Promptfoo",
        description="Test and red-team prompts, agents and RAG pipelines from the command line or CI.",
        category="Evaluation",
        tech_stack=["TypeScript", "Node.js"],
        github_stars=24073,
        url="https://github.com/promptfoo/promptfoo",
        use_case="Prompt testing and red teaming"
    ),
    Agent(
        name="OpenLLMetry",
        description="OpenTelemetry-based instrumentation for LLM applications, exporting to any observability backend.",
        category="Evaluation",
        tech_stack=["Python", "OpenTelemetry"],
        github_stars=7364,
        url="https://github.com/traceloop/openllmetry",
        use_case="Standard telemetry for LLM apps"
    ),
    Agent(
        name="Opik",
        description="Comet's platform for debugging, evaluating and monitoring LLM and RAG applications in production.",
        category="Evaluation",
        tech_stack=["Python", "TypeScript"],
        github_stars=21232,
        url="https://github.com/comet-ml/opik",
        use_case="Production monitoring of LLM apps"
    ),
    Agent(
        name="Ragas",
        description="Metrics for evaluating retrieval-augmented pipelines, including faithfulness and context precision.",
        category="Evaluation",
        tech_stack=["Python", "LangChain"],
        github_stars=15201,
        url="https://github.com/explodinggradients/ragas",
        use_case="Measuring RAG quality"
    ),
    Agent(
        name="Giskard",
        description="Open source testing library that scans LLM agents for hallucination, bias and prompt injection.",
        category="Evaluation",
        tech_stack=["Python", "ML"],
        github_stars=5741,
        url="https://github.com/Giskard-AI/giskard",
        use_case="Automated vulnerability scanning for models"
    ),
    Agent(
        name="Guardrails",
        description="Adds validation and structure to LLM output, re-asking the model when a check fails.",
        category="Safety",
        tech_stack=["Python", "Pydantic"],
        github_stars=7260,
        url="https://github.com/guardrails-ai/guardrails",
        use_case="Validating and correcting model output"
    ),
    Agent(
        name="NeMo Guardrails",
        description="NVIDIA's toolkit for adding programmable conversational rails to LLM applications.",
        category="Safety",
        tech_stack=["Python", "Colang"],
        github_stars=6895,
        url="https://github.com/NVIDIA/NeMo-Guardrails",
        use_case="Constraining what a chatbot will discuss"
    ),
    Agent(
        name="Rebuff",
        description="A prompt injection detector that layers heuristics, an LLM check and a vector database of known attacks.",
        category="Safety",
        tech_stack=["Python", "Vector DB"],
        github_stars=1517,
        url="https://github.com/protectai/rebuff",
        use_case="Detecting prompt injection"
    ),
    Agent(
        name="Garak",
        description="A vulnerability scanner for LLMs, probing for jailbreaks, data leakage and toxic generation.",
        category="Safety",
        tech_stack=["Python"],
        github_stars=8739,
        url="https://github.com/leondz/garak",
        use_case="Red teaming a model before deployment"
    ),
    Agent(
        name="Presidio",
        description="Microsoft's framework for detecting and redacting personal data in text and images.",
        category="Safety",
        tech_stack=["Python", "spaCy"],
        github_stars=10395,
        url="https://github.com/microsoft/presidio",
        use_case="Stripping PII before it reaches a model"
    ),
    Agent(
        name="LiteLLM",
        description="A gateway that exposes one OpenAI-compatible API across a hundred model providers, with budgets and fallbacks.",
        category="Framework",
        tech_stack=["Python", "Rust", "Proxy"],
        github_stars=55917,
        url="https://github.com/BerriAI/litellm",
        use_case="Provider-agnostic model access"
    ),
    Agent(
        name="Chroma",
        description="An embedding database designed for AI applications, with a Python-first API and local persistence.",
        category="Infrastructure",
        tech_stack=["Python", "Rust", "SQLite"],
        github_stars=28987,
        url="https://github.com/chroma-core/chroma",
        use_case="Local vector storage for RAG"
    ),
    Agent(
        name="Qdrant",
        description="A high-performance vector database with rich payload filtering alongside similarity search.",
        category="Infrastructure",
        tech_stack=["Rust", "gRPC"],
        github_stars=33870,
        url="https://github.com/qdrant/qdrant",
        use_case="Filtered vector search at scale"
    ),
    Agent(
        name="Weaviate",
        description="An open source vector database that stores both objects and vectors, with built-in hybrid search.",
        category="Infrastructure",
        tech_stack=["Go", "GraphQL"],
        github_stars=16708,
        url="https://github.com/weaviate/weaviate",
        use_case="Hybrid keyword and vector search"
    ),
    Agent(
        name="Milvus",
        description="A cloud-native vector database built for billion-scale similarity search.",
        category="Infrastructure",
        tech_stack=["Go", "C++", "Kubernetes"],
        github_stars=45568,
        url="https://github.com/milvus-io/milvus",
        use_case="Very large scale vector search"
    ),
    Agent(
        name="pgvector",
        description="Vector similarity search inside PostgreSQL, so embeddings live beside the rest of your data.",
        category="Infrastructure",
        tech_stack=["C", "PostgreSQL"],
        github_stars=22543,
        url="https://github.com/pgvector/pgvector",
        use_case="Vector search without a separate database"
    ),
    Agent(
        name="FAISS",
        description="Meta's library for efficient similarity search over dense vectors, and the index behind this project.",
        category="Infrastructure",
        tech_stack=["C++", "Python"],
        github_stars=40696,
        url="https://github.com/facebookresearch/faiss",
        use_case="In-process vector indexing"
    ),
    Agent(
        name="Ollama",
        description="Runs open language models locally with a simple CLI and HTTP API. Powers this project's embeddings.",
        category="Infrastructure",
        tech_stack=["Go", "llama.cpp"],
        github_stars=178091,
        url="https://github.com/ollama/ollama",
        use_case="Running models on your own machine"
    ),
    Agent(
        name="vLLM",
        description="A high-throughput inference engine using paged attention to serve models efficiently.",
        category="Infrastructure",
        tech_stack=["Python", "CUDA"],
        github_stars=88563,
        url="https://github.com/vllm-project/vllm",
        use_case="Serving models at high throughput"
    ),
    Agent(
        name="Unsloth",
        description="Fine-tunes language models several times faster and with far less memory through custom kernels.",
        category="Fine-tuning",
        tech_stack=["Python", "Triton", "CUDA"],
        github_stars=69775,
        url="https://github.com/unslothai/unsloth",
        use_case="Fast low-memory fine-tuning"
    ),
    Agent(
        name="LLaMA-Factory",
        description="A unified framework for fine-tuning a hundred-plus language and vision models, with a web UI.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "LoRA"],
        github_stars=73949,
        url="https://github.com/hiyouga/LLaMA-Factory",
        use_case="Fine-tuning many model families from one tool"
    ),
    Agent(
        name="Axolotl",
        description="Configuration-driven fine-tuning: describe the run in YAML rather than writing training code.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "DeepSpeed"],
        github_stars=12331,
        url="https://github.com/axolotl-ai-cloud/axolotl",
        use_case="Reproducible fine-tuning runs"
    ),
    Agent(
        name="PEFT",
        description="Hugging Face's parameter-efficient fine-tuning library, including LoRA and QLoRA adapters.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "Transformers"],
        github_stars=21523,
        url="https://github.com/huggingface/peft",
        use_case="Adapter-based fine-tuning"
    ),
    Agent(
        name="TRL",
        description="Trains language models with reinforcement learning, covering SFT, DPO and PPO.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "Transformers"],
        github_stars=19030,
        url="https://github.com/huggingface/trl",
        use_case="Preference and reward-based training"
    ),
    Agent(
        name="Argilla",
        description="A collaboration tool for building and curating the datasets that fine-tuning and evaluation need.",
        category="Fine-tuning",
        tech_stack=["Python", "Elasticsearch"],
        github_stars=5078,
        url="https://github.com/argilla-io/argilla",
        use_case="Human feedback and dataset curation"
    ),
    Agent(
        name="SDV",
        description="Generates synthetic tabular data that preserves the statistical shape of the original.",
        category="Data Analysis",
        tech_stack=["Python", "Pandas", "ML"],
        github_stars=3541,
        url="https://github.com/sdv-dev/SDV",
        use_case="Synthetic datasets for testing"
    ),
    Agent(
        name="Metaflow",
        description="Netflix's framework for building and deploying data and ML workflows from notebook to production.",
        category="Infrastructure",
        tech_stack=["Python", "AWS", "Kubernetes"],
        github_stars=10206,
        url="https://github.com/Netflix/metaflow",
        use_case="Productionising ML pipelines"
    ),
    Agent(
        name="Whisper",
        description="OpenAI's speech recognition model, robust across accents, background noise and languages.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=106984,
        url="https://github.com/openai/whisper",
        use_case="Transcribing audio"
    ),
    Agent(
        name="Faster Whisper",
        description="A CTranslate2 reimplementation of Whisper that transcribes several times faster for less memory.",
        category="Multimodal",
        tech_stack=["Python", "CTranslate2"],
        github_stars=24833,
        url="https://github.com/SYSTRAN/faster-whisper",
        use_case="Fast local transcription"
    ),
    Agent(
        name="Coqui TTS",
        description="A deep learning toolkit for text-to-speech, with voice cloning and dozens of pretrained voices.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=45872,
        url="https://github.com/coqui-ai/TTS",
        use_case="Speech synthesis and voice cloning"
    ),
    Agent(
        name="ComfyUI",
        description="A node-based interface for diffusion models, where the whole generation graph is explicit.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=125727,
        url="https://github.com/comfyanonymous/ComfyUI",
        use_case="Composable image generation pipelines"
    ),
    Agent(
        name="Stable Diffusion WebUI",
        description="A browser interface for Stable Diffusion with an extensive extension ecosystem.",
        category="Multimodal",
        tech_stack=["Python", "Gradio", "PyTorch"],
        github_stars=164462,
        url="https://github.com/AUTOMATIC1111/stable-diffusion-webui",
        use_case="Local image generation"
    ),
    Agent(
        name="CLIP",
        description="Joint text and image embeddings, the basis for most image search and captioning pipelines.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=34150,
        url="https://github.com/openai/CLIP",
        use_case="Image and text similarity search"
    ),
    Agent(
        name="Pipecat",
        description="A framework for realtime voice and multimodal agents, handling turn-taking and interruption.",
        category="Customer Service",
        tech_stack=["Python", "WebRTC"],
        github_stars=14031,
        url="https://github.com/pipecat-ai/pipecat",
        use_case="Realtime conversational agents"
    ),
    Agent(
        name="LiveKit Agents",
        description="Builds realtime voice AI agents on WebRTC, with telephony and streaming built in.",
        category="Customer Service",
        tech_stack=["Python", "WebRTC", "Node.js"],
        github_stars=12850,
        url="https://github.com/livekit/agents",
        use_case="Voice agents over phone and web"
    ),
    Agent(
        name="Pydantic AI",
        description="An agent framework that uses Pydantic models for structured, validated tool arguments and outputs.",
        category="Framework",
        tech_stack=["Python", "Pydantic"],
        github_stars=19181,
        url="https://github.com/pydantic/pydantic-ai",
        use_case="Type-safe agent development"
    ),
    Agent(
        name="OpenAI Agents SDK",
        description="A small framework for multi-agent workflows, with handoffs, guardrails and tracing built in.",
        category="Framework",
        tech_stack=["Python", "OpenAI API"],
        github_stars=28516,
        url="https://github.com/openai/openai-agents-python",
        use_case="Multi-agent handoffs and tracing"
    ),
    Agent(
        name="Agno",
        description="A framework for building and running agent platforms, with memory, knowledge and tools included.",
        category="Framework",
        tech_stack=["Python", "Vector DB"],
        github_stars=41638,
        url="https://github.com/agno-agi/agno",
        use_case="Full-stack agent platforms"
    ),
    Agent(
        name="MCP Servers",
        description="The reference collection of Model Context Protocol servers, giving agents access to external systems.",
        category="Framework",
        tech_stack=["TypeScript", "Python", "MCP"],
        github_stars=89384,
        url="https://github.com/modelcontextprotocol/servers",
        use_case="Connecting agents to tools and data"
    ),
    Agent(
        name="Superagent",
        description="A runtime that guards AI applications against prompt injection, data exfiltration and unsafe tool calls.",
        category="Safety",
        tech_stack=["TypeScript", "Python"],
        github_stars=6708,
        url="https://github.com/superagent-ai/superagent",
        use_case="Runtime protection for agents"
    ),
    Agent(
        name="Portkey Gateway",
        description="A fast AI gateway with routing, retries, caching and guardrails across many model providers.",
        category="Infrastructure",
        tech_stack=["TypeScript", "Hono"],
        github_stars=12676,
        url="https://github.com/Portkey-AI/gateway",
        use_case="Reliable multi-provider model access"
    ),
    Agent(
        name="BentoML",
        description="Packages models and AI applications into production services with batching and autoscaling.",
        category="Infrastructure",
        tech_stack=["Python", "Docker", "Kubernetes"],
        github_stars=8774,
        url="https://github.com/bentoml/BentoML",
        use_case="Serving models as production APIs"
    ),
    Agent(
        name="Ray",
        description="A distributed compute engine for scaling Python and AI workloads across a cluster.",
        category="Infrastructure",
        tech_stack=["Python", "C++", "Kubernetes"],
        github_stars=43481,
        url="https://github.com/ray-project/ray",
        use_case="Distributed training and inference"
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

        agents = [_build_agent(record, i) for i, record in enumerate(records)]
        _warn_about_duplicates(agents)
        if agents:
            logger.info("Loaded %d agents from %s", len(agents), config.AGENTS_JSON)
        else:
            # An existing but empty file is a deliberate state — somebody
            # removed every agent. Falling back to the samples here would
            # silently repopulate the index with data they just deleted.
            logger.warning("%s is empty; the index will have no agents.", config.AGENTS_JSON)
        return agents

    logger.info("No catalogue at %s; using %d built-in sample agents.",
                config.AGENTS_JSON, len(SAMPLE_AGENTS))
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
