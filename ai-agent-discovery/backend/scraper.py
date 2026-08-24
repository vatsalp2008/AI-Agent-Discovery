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
        url="https://cursor.com",
        use_case="Code editing, refactoring, generation"
    ),
    Agent(
        name="Aider",
        description="A command line tool that lets you pair program with GPT-3.5/4. Edits code in your local git repo.",
        category="Code Generation",
        tech_stack=["Python", "GPT-4", "Git"],
        github_stars=12000,
        url="https://github.com/Aider-AI/aider",
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
        tech_stack=["Rust", "Python"],
        github_stars=45000,
        url="https://github.com/openinterpreter/openinterpreter",
        use_case="Local system control, script execution"
    ),
    Agent(
        name="AutoGPT",
        description="An experimental open-source attempt to make GPT-4 fully autonomous.",
        category="Autonomous Agent",
        tech_stack=["Python", "GPT-4", "Pinecone"],
        github_stars=160000,
        url="https://github.com/Significant-Gravitas/AutoGPT",
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
    Agent(
        name="PandasAI",
        description="A Python library that integrates generative artificial intelligence capabilities into pandas, making dataframes conversational.",
        category="Data Analysis",
        tech_stack=["Python", "Pandas", "LLMs"],
        github_stars=11000,
        url="https://github.com/sinaptik-ai/pandas-ai",
        use_case="Asking a dataframe questions in English"
    ),
    Agent(
        name="Vanna AI",
        description="Retrieval-augmented text-to-SQL: ask questions in plain English and get SQL that runs against your warehouse.",
        category="Data Analysis",
        tech_stack=["Python", "RAG", "SQL"],
        github_stars=19000,
        url="https://github.com/vanna-ai/vanna",
        use_case="Natural language querying of databases",
        status="archived",
        alternatives=["WrenAI", "Chat2DB", "DB-GPT"]
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
        use_case="Automatic chart and infographic generation",
        status="dormant"
    ),
    Agent(
        name="Sketch",
        description="An AI coding assistant for pandas that understands the contents of a dataframe, not just its schema.",
        category="Data Analysis",
        tech_stack=["Python", "Pandas"],
        github_stars=2300,
        url="https://github.com/approximatelabs/sketch",
        use_case="Dataframe-aware code suggestions",
        status="dormant"
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
        name="Devin Desktop",
        description="A desktop surface for managing fleets of local and cloud coding agents: plan, delegate, review and ship. Formerly Windsurf.",
        category="Code Generation",
        tech_stack=["Electron", "TypeScript"],
        github_stars=0,
        url="https://devin.ai/desktop",
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
        url="https://www.coderabbit.ai",
        use_case="Automated pull request review"
    ),
    Agent(
        name="RAGFlow",
        description="A RAG engine built on deep document understanding, with layout-aware chunking and grounded citations.",
        category="Research",
        tech_stack=["Python", "Go", "Elasticsearch", "Docker"],
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
        use_case="Retrieval chat with citations",
        status="archived",
        alternatives=["RAGFlow", "Onyx"]
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
        use_case="Voice agents and phone calls",
        status="dormant"
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
        use_case="Explaining Kubernetes errors in plain English"
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
        url="https://github.com/vibrantlabsai/ragas",
        use_case="Measuring RAG quality"
    ),
    Agent(
        name="Giskard",
        description="Open source testing library that scans LLM agents for hallucination, bias and prompt injection.",
        category="Evaluation",
        tech_stack=["Python", "ML"],
        github_stars=5741,
        url="https://github.com/Giskard-AI/giskard-oss",
        use_case="Scanning an agent for hallucination and bias"
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
        url="https://github.com/NVIDIA-NeMo/Guardrails",
        use_case="Programmable dialogue rails in Colang"
    ),
    Agent(
        name="Rebuff",
        description="A prompt injection detector that layers heuristics, an LLM check and a vector database of known attacks.",
        category="Safety",
        tech_stack=["Python", "TypeScript"],
        github_stars=1517,
        url="https://github.com/protectai/rebuff",
        use_case="Detecting prompt injection",
        status="archived",
        alternatives=["AgentDojo", "PurpleLlama"]
    ),
    Agent(
        name="Garak",
        description="A vulnerability scanner for LLMs, probing for jailbreaks, data leakage and toxic generation.",
        category="Safety",
        tech_stack=["Python"],
        github_stars=8739,
        url="https://github.com/NVIDIA/garak",
        use_case="Scanning a model for known weaknesses"
    ),
    Agent(
        name="Presidio",
        description="Microsoft's framework for detecting and redacting personal data in text and images.",
        category="Safety",
        tech_stack=["Python", "spaCy"],
        github_stars=10395,
        url="https://github.com/data-privacy-stack/presidio",
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
        description="Fine-tunes language models on a single consumer GPU, several times faster and with far less memory, through custom kernels.",
        category="Fine-tuning",
        tech_stack=["Python", "Triton", "CUDA"],
        github_stars=69775,
        url="https://github.com/unslothai/unsloth",
        use_case="Fine-tuning on one GPU"
    ),
    Agent(
        name="LLaMA-Factory",
        description="A unified framework for fine-tuning a hundred-plus language and vision models, with a web UI.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "LoRA"],
        github_stars=73949,
        url="https://github.com/hiyouga/LlamaFactory",
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
        description="Hugging Face's parameter-efficient fine-tuning library: LoRA and QLoRA adapters train a fraction of the weights, so a large model fits on one GPU.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "Transformers"],
        github_stars=21523,
        url="https://github.com/huggingface/peft",
        use_case="Adapter fine-tuning on one GPU"
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
        use_case="Taking a notebook workflow to production"
    ),
    Agent(
        name="Whisper",
        description="OpenAI's speech-to-text model, robust across accents, background noise and languages.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=106984,
        url="https://github.com/openai/whisper",
        use_case="Transcribing speech to text"
    ),
    Agent(
        name="Faster Whisper",
        description="A CTranslate2 reimplementation of Whisper that turns speech into text several times faster for less memory.",
        category="Multimodal",
        tech_stack=["Python", "CTranslate2"],
        github_stars=24833,
        url="https://github.com/SYSTRAN/faster-whisper",
        use_case="Fast local speech-to-text"
    ),
    Agent(
        name="Coqui TTS",
        description="A deep learning toolkit for text-to-speech, with voice cloning and dozens of pretrained voices; carried on as idiap/coqui-ai-TTS since the company closed.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=45872,
        url="https://github.com/coqui-ai/TTS",
        use_case="Training and running text-to-speech models",
        status="dormant"
    ),
    Agent(
        name="ComfyUI",
        description="A node-based interface for diffusion models, where the whole generation graph is explicit.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=125727,
        url="https://github.com/Comfy-Org/ComfyUI",
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
        use_case="Reference Model Context Protocol servers"
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
        name="Langflow",
        description="A visual builder for LLM applications and agents, where flows are wired up on a canvas.",
        category="Framework",
        tech_stack=["Python", "React"],
        github_stars=153024,
        url="https://github.com/langflow-ai/langflow",
        use_case="Building agent flows without writing code"
    ),
    Agent(
        name="Marvin",
        description="A library for folding AI into ordinary Python: typed functions, classifiers and extractors.",
        category="Framework",
        tech_stack=["Python", "Pydantic"],
        github_stars=6188,
        url="https://github.com/PrefectHQ/marvin",
        use_case="AI as ordinary typed functions"
    ),
    Agent(
        name="GraphRAG",
        description="Builds a knowledge graph from documents so retrieval can answer questions spanning many sources.",
        category="Research",
        tech_stack=["Python", "Graph", "LLM"],
        github_stars=35388,
        url="https://github.com/microsoft/graphrag",
        use_case="Question answering across whole corpora"
    ),
    Agent(
        name="DSPy",
        description="Programs language models with declarative modules and optimises the prompts for you.",
        category="Framework",
        tech_stack=["Python", "ML"],
        github_stars=37030,
        url="https://github.com/stanfordnlp/dspy",
        use_case="Optimising prompts programmatically"
    ),
    Agent(
        name="ScrapeGraphAI",
        description="Scrapes websites by describing what you want rather than writing selectors.",
        category="Automation",
        tech_stack=["Python", "Playwright", "Graph"],
        github_stars=29320,
        url="https://github.com/ScrapeGraphAI/Scrapegraph-ai",
        use_case="Structured extraction from web pages"
    ),
    Agent(
        name="Jina Reader",
        description="Turns any URL into clean, LLM-friendly text, stripping navigation and boilerplate.",
        category="Research",
        tech_stack=["TypeScript", "Puppeteer"],
        github_stars=11845,
        url="https://github.com/jina-ai/reader",
        use_case="Turning a web page into clean text"
    ),
    Agent(
        name="MarkItDown",
        description="Converts PDFs, Office documents, images and audio into Markdown for language models.",
        category="Framework",
        tech_stack=["Python", "OCR"],
        github_stars=172891,
        url="https://github.com/microsoft/markitdown",
        use_case="Normalising documents before indexing"
    ),
    Agent(
        name="Docling",
        description="Parses documents with layout understanding, preserving tables and reading order for RAG.",
        category="Framework",
        tech_stack=["Python", "PyTorch", "OCR"],
        github_stars=64546,
        url="https://github.com/docling-project/docling",
        use_case="Layout-aware document parsing"
    ),
    Agent(
        name="llama.cpp",
        description="Runs language models in plain C/C++ with quantisation, from laptops down to phones.",
        category="Infrastructure",
        tech_stack=["C++", "GGUF"],
        github_stars=123333,
        url="https://github.com/ggml-org/llama.cpp",
        use_case="Inference on modest hardware"
    ),
    Agent(
        name="MLC LLM",
        description="Compiles models for whatever hardware you have, including browsers and mobile GPUs.",
        category="Infrastructure",
        tech_stack=["Python", "TVM", "WebGPU"],
        github_stars=23049,
        url="https://github.com/mlc-ai/mlc-llm",
        use_case="Deploying models to edge devices"
    ),
    Agent(
        name="MLX",
        description="Apple's array framework for machine learning on Apple silicon, with a NumPy-like API.",
        category="Infrastructure",
        tech_stack=["Python", "C++", "Metal"],
        github_stars=27898,
        url="https://github.com/ml-explore/mlx",
        use_case="Training and inference on Apple silicon"
    ),
    Agent(
        name="LeRobot",
        description="Models, datasets and tools for real-world robotics, bringing imitation learning within reach.",
        category="Robotics",
        tech_stack=["Python", "PyTorch"],
        github_stars=26550,
        url="https://github.com/huggingface/lerobot",
        use_case="Training robot policies"
    ),
    Agent(
        name="PaperQA",
        description="Answers questions over scientific papers with citations, built for accuracy over fluency.",
        category="Research",
        tech_stack=["Python", "RAG"],
        github_stars=9011,
        url="https://github.com/Future-House/paper-qa",
        use_case="Literature review with citations"
    ),
    Agent(
        name="Nougat",
        description="Reads academic PDFs into markup, recovering equations and tables that plain OCR loses.",
        category="Research",
        tech_stack=["Python", "PyTorch", "OCR"],
        github_stars=10056,
        url="https://github.com/facebookresearch/nougat",
        use_case="Parsing scientific papers",
        status="dormant"
    ),
    Agent(
        name="Swarm",
        description="OpenAI's teaching framework for lightweight multi-agent coordination and handoffs.",
        category="Framework",
        tech_stack=["Python", "OpenAI API"],
        github_stars=21890,
        url="https://github.com/openai/swarm",
        use_case="Learning multi-agent patterns"
    ),
    Agent(
        name="A2A",
        description="Google's Agent2Agent protocol, a standard for agents built by different vendors to interoperate.",
        category="Framework",
        tech_stack=["Protocol", "JSON-RPC"],
        github_stars=25275,
        url="https://github.com/a2aproject/A2A",
        use_case="Cross-vendor agent communication"
    ),
    Agent(
        name="Isaac Lab",
        description="NVIDIA's framework for robot learning in simulation, with GPU-accelerated physics and parallel environments.",
        category="Robotics",
        tech_stack=["Python", "Isaac Sim", "CUDA"],
        github_stars=7870,
        url="https://github.com/isaac-sim/IsaacLab",
        use_case="Training robot policies in simulation"
    ),
    Agent(
        name="MuJoCo",
        description="A physics engine for contact-rich simulation, widely used to train and evaluate control policies.",
        category="Robotics",
        tech_stack=["C", "C++", "Python"],
        github_stars=14507,
        url="https://github.com/google-deepmind/mujoco",
        use_case="Physics simulation for control research"
    ),
    Agent(
        name="Gymnasium",
        description="The standard API for reinforcement learning environments, and the successor to OpenAI Gym.",
        category="Robotics",
        tech_stack=["Python", "NumPy"],
        github_stars=12307,
        url="https://github.com/Farama-Foundation/Gymnasium",
        use_case="Standard interface for RL environments"
    ),
    Agent(
        name="Isaac GR00T",
        description="NVIDIA's open foundation model for generalist humanoid robots, taking language and vision to actions.",
        category="Robotics",
        tech_stack=["Python", "PyTorch", "VLA"],
        github_stars=7789,
        url="https://github.com/NVIDIA/Isaac-GR00T",
        use_case="Foundation model for humanoid control"
    ),
    Agent(
        name="Habitat Lab",
        description="Trains embodied agents to navigate and manipulate in photorealistic indoor simulations.",
        category="Robotics",
        tech_stack=["Python", "PyTorch"],
        github_stars=3095,
        url="https://github.com/facebookresearch/habitat-lab",
        use_case="Embodied navigation research"
    ),
    Agent(
        name="Nav2",
        description="The ROS 2 navigation stack: planning, control and recovery behaviours for mobile robots.",
        category="Robotics",
        tech_stack=["C++", "ROS 2"],
        github_stars=4572,
        url="https://github.com/ros-navigation/navigation2",
        use_case="Autonomous navigation for mobile robots"
    ),
    Agent(
        name="MLflow",
        description="Tracks experiments, packages models and manages their lifecycle, now including LLM evaluation.",
        category="MLOps",
        tech_stack=["Python", "REST"],
        github_stars=27471,
        url="https://github.com/mlflow/mlflow",
        use_case="Experiment tracking and model registry"
    ),
    Agent(
        name="Weights & Biases",
        description="Logs experiments, datasets and model artifacts, with tracing for LLM and agent runs.",
        category="MLOps",
        tech_stack=["Python", "SaaS"],
        github_stars=11228,
        url="https://github.com/wandb/wandb",
        use_case="Experiment tracking and comparison"
    ),
    Agent(
        name="DVC",
        description="Version control for datasets and models, keeping large files out of git while staying reproducible.",
        category="MLOps",
        tech_stack=["Python", "Git"],
        github_stars=15808,
        url="https://github.com/treeverse/dvc",
        use_case="Versioning data alongside code"
    ),
    Agent(
        name="Great Expectations",
        description="Declares what your data should look like and fails loudly when it does not.",
        category="MLOps",
        tech_stack=["Python", "SQL"],
        github_stars=11706,
        url="https://github.com/fivetran/great_expectations",
        use_case="Data quality checks in a pipeline"
    ),
    Agent(
        name="Evidently",
        description="Monitors ML and LLM systems in production, reporting drift and quality regressions.",
        category="MLOps",
        tech_stack=["Python", "Pandas"],
        github_stars=7797,
        url="https://github.com/evidentlyai/evidently",
        use_case="Detecting drift after deployment"
    ),
    Agent(
        name="whylogs",
        description="Logs statistical profiles of data rather than the data itself, so monitoring does not copy your dataset.",
        category="MLOps",
        tech_stack=["Python", "Protobuf"],
        github_stars=2830,
        url="https://github.com/whylabs/whylogs",
        use_case="Privacy-preserving data monitoring",
        status="dormant"
    ),
    Agent(
        name="Qwen-Agent",
        description="Alibaba's agent framework built around Qwen, with tool use, code interpreter and browser assistant.",
        category="Framework",
        tech_stack=["Python", "Qwen"],
        github_stars=16952,
        url="https://github.com/QwenLM/Qwen-Agent",
        use_case="Building agents on Qwen models"
    ),
    Agent(
        name="CAMEL",
        description="A framework for studying multi-agent societies, where agents role-play to solve a task together.",
        category="Autonomous Agent",
        tech_stack=["Python", "Multi-Agent"],
        github_stars=17574,
        url="https://github.com/camel-ai/camel",
        use_case="Researching agent collaboration"
    ),
    Agent(
        name="XAgent",
        description="An autonomous agent that decomposes complex tasks into subtasks and runs them in a sandbox.",
        category="Autonomous Agent",
        tech_stack=["Python", "Docker"],
        github_stars=8531,
        url="https://github.com/OpenBMB/XAgent",
        use_case="Autonomous execution of complex tasks"
    ),
    Agent(
        name="TransformerLens",
        description="A library for mechanistic interpretability: inspect and intervene on the internals of a transformer.",
        category="Evaluation",
        tech_stack=["Python", "PyTorch"],
        github_stars=3777,
        url="https://github.com/TransformerLensOrg/TransformerLens",
        use_case="Mechanistic interpretability research"
    ),
    Agent(
        name="torchtune",
        description="PyTorch's native library for post-training: fine-tuning, distillation and RLHF recipes.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch"],
        github_stars=5797,
        url="https://github.com/meta-pytorch/torchtune",
        use_case="Fine-tuning with PyTorch-native recipes"
    ),
    Agent(
        name="LibreChat",
        description="A self-hosted chat interface supporting many providers, with agents, tools and multi-user accounts.",
        category="Customer Service",
        tech_stack=["TypeScript", "MongoDB", "React"],
        github_stars=41925,
        url="https://github.com/danny-avila/LibreChat",
        use_case="Self-hosted chat across providers"
    ),
    Agent(
        name="Open WebUI",
        description="A self-hosted interface for local models, with RAG over your documents and a plugin system.",
        category="Infrastructure",
        tech_stack=["Python", "Svelte", "Ollama"],
        github_stars=148501,
        url="https://github.com/open-webui/open-webui",
        use_case="A front end for locally-run models"
    ),
    Agent(
        name="LobeHub",
        description="A chat framework with plugins, function calling and multi-modal input across many providers.",
        category="Customer Service",
        tech_stack=["TypeScript", "Next.js"],
        github_stars=81504,
        url="https://github.com/lobehub/lobehub",
        use_case="Extensible chat with plugins"
    ),
    Agent(
        name="OpenCode",
        description="An open source terminal coding agent that works with any model provider.",
        category="Code Generation",
        tech_stack=["TypeScript", "Go"],
        github_stars=196186,
        url="https://github.com/anomalyco/opencode",
        use_case="Provider-agnostic terminal coding"
    ),
    Agent(
        name="AgentGPT",
        description="Assemble and deploy autonomous agents from the browser, watching them plan and execute in the open.",
        category="Autonomous Agent",
        tech_stack=["TypeScript", "Next.js", "Python"],
        github_stars=36304,
        url="https://github.com/reworkd/AgentGPT",
        use_case="Running autonomous agents in a browser",
        status="archived",
        alternatives=["AutoGPT", "Suna"]
    ),
    Agent(
        name="E2B",
        description="Secure cloud sandboxes where an AI agent can run code it wrote without touching your machine.",
        category="Infrastructure",
        tech_stack=["Python", "TypeScript", "Firecracker"],
        github_stars=13355,
        url="https://github.com/e2b-dev/E2B",
        use_case="Sandboxed execution of generated code"
    ),
    Agent(
        name="Firecrawl",
        description="Turns websites into clean, structured data for agents, handling crawling, scraping and extraction.",
        category="Automation",
        tech_stack=["TypeScript", "Playwright"],
        github_stars=165821,
        url="https://github.com/firecrawl/firecrawl",
        use_case="Web data extraction for agents"
    ),
    Agent(
        name="SiYuan",
        description="A privacy-first knowledge base that keeps notes local and answers questions over them.",
        category="Research",
        tech_stack=["Go", "TypeScript"],
        github_stars=45741,
        url="https://github.com/siyuan-note/siyuan",
        use_case="Local-first personal knowledge base"
    ),
    Agent(
        name="OpenAdapt",
        description="Records a demonstrated GUI workflow and replays it, generalising across applications.",
        category="Automation",
        tech_stack=["Python", "Vision"],
        github_stars=1673,
        url="https://github.com/OpenAdaptAI/OpenAdapt",
        use_case="Automating desktop workflows by demonstration"
    ),
    Agent(
        name="UFO",
        description="Microsoft's agent for driving Windows applications through their own user interfaces.",
        category="Automation",
        tech_stack=["Python", "Windows", "Vision"],
        github_stars=9453,
        url="https://github.com/microsoft/UFO",
        use_case="Operating Windows applications"
    ),
    Agent(
        name="Cloudflare Agents",
        description="A framework for agents that run at the edge, with durable state and scheduled execution.",
        category="Framework",
        tech_stack=["TypeScript", "Workers"],
        github_stars=5423,
        url="https://github.com/cloudflare/agents",
        use_case="Deploying agents to the edge"
    ),
    Agent(
        name="Parler TTS",
        description="A text-to-speech library where the voice, tone and pacing are described in plain language.",
        category="Multimodal",
        tech_stack=['Python', 'PyTorch'],
        github_stars=5587,
        url="https://github.com/huggingface/parler-tts",
        use_case="Describing a voice in plain language",
        status="dormant"
    ),
    Agent(
        name="WhisperX",
        description="Speech-to-text with word-level timestamps and speaker diarisation on top of Whisper.",
        category="Multimodal",
        tech_stack=['Python', 'PyTorch'],
        github_stars=23546,
        url="https://github.com/m-bain/whisperX",
        use_case="Transcription with speaker labels"
    ),
    Agent(
        name="Bark",
        description="A generative audio model that produces speech, music and sound effects from text prompts.",
        category="Multimodal",
        tech_stack=['Python', 'PyTorch'],
        github_stars=39236,
        url="https://github.com/suno-ai/bark",
        use_case="Generating speech and sound from text",
        status="dormant"
    ),
    Agent(
        name="SeamlessM4T",
        description="Meta's foundation model for speech and text translation across roughly a hundred languages.",
        category="Multimodal",
        tech_stack=['Python', 'PyTorch'],
        github_stars=11839,
        url="https://github.com/facebookresearch/seamless_communication",
        use_case="Multilingual speech translation"
    ),
    Agent(
        name="LLaVA",
        description="A visual instruction-tuned assistant that answers questions about images.",
        category="Multimodal",
        tech_stack=['Python', 'PyTorch', 'Vision'],
        github_stars=24977,
        url="https://github.com/haotian-liu/LLaVA",
        use_case="Visual question answering",
        status="dormant"
    ),
    Agent(
        name="Qwen3-VL",
        description="Alibaba's multimodal model family, reading documents, charts and video alongside text.",
        category="Multimodal",
        tech_stack=['Python', 'PyTorch', 'Vision'],
        github_stars=19778,
        url="https://github.com/QwenLM/Qwen3-VL",
        use_case="Document and video understanding"
    ),
    Agent(
        name="PurpleLlama",
        description="Meta's tools for assessing and improving LLM safety, including input and output guardrails.",
        category="Safety",
        tech_stack=['Python', 'PyTorch'],
        github_stars=4344,
        url="https://github.com/meta-llama/PurpleLlama",
        use_case="Input and output guardrails for Llama"
    ),
    Agent(
        name="PyRIT",
        description="Microsoft's risk identification toolkit for automating red-team probes against generative systems.",
        category="Safety",
        tech_stack=['Python'],
        github_stars=114,
        url="https://github.com/microsoft/PyRIT",
        use_case="Orchestrating automated attack probes"
    ),
    Agent(
        name="Kubeflow",
        description="Runs machine learning workflows on Kubernetes, from notebooks through pipelines to serving.",
        category="MLOps",
        tech_stack=['Python', 'Kubernetes', 'Go'],
        github_stars=15811,
        url="https://github.com/kubeflow/kubeflow",
        use_case="ML workflows on Kubernetes"
    ),
    Agent(
        name="ZenML",
        description="A portable pipeline framework that keeps ML code the same across local runs and cloud stacks.",
        category="MLOps",
        tech_stack=['Python', 'Docker'],
        github_stars=5553,
        url="https://github.com/zenml-io/zenml",
        use_case="Portable ML pipelines"
    ),
    Agent(
        name="Dagster",
        description="An orchestrator built around data assets, with typed inputs and lineage across pipelines.",
        category="MLOps",
        tech_stack=['Python', 'React'],
        github_stars=15978,
        url="https://github.com/dagster-io/dagster",
        use_case="Asset-aware data orchestration"
    ),
    Agent(
        name="OpenLLM",
        description="Serves open models behind an OpenAI-compatible API, with quantisation and cloud deployment.",
        category="Infrastructure",
        tech_stack=['Python', 'BentoML'],
        github_stars=12482,
        url="https://github.com/bentoml/OpenLLM",
        use_case="Self-hosted model serving"
    ),
    Agent(
        name="MetaGPT",
        description="Assigns a software team's roles to separate agents, turning one line of requirement into a design, tasks and a repository.",
        category="Autonomous Agent",
        tech_stack=["Python", "Multi-Agent"],
        github_stars=38000,
        url="https://github.com/FoundationAgents/MetaGPT",
        use_case="Multi-agent software development"
    ),
    Agent(
        name="LangChain",
        description="A framework for composing LLM applications from chains, agents and tools, with integrations for most models and vector stores.",
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
        url="https://github.com/crewAIInc/crewAI",
        use_case="Multi-agent orchestration"
    ),
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
    Agent(
        name="SuperAGI",
        description="Runs and monitors several autonomous agents at once from a dashboard, with tools, telemetry and the ability to pause one mid-run.",
        category="Autonomous Agent",
        tech_stack=["Python", "Docker", "PostgreSQL"],
        github_stars=14500,
        url="https://github.com/TransformerOptimus/SuperAGI",
        use_case="Running concurrent agents from a dashboard",
        status="dormant"
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
        url="https://github.com/zylon-ai/private-gpt",
        use_case="Document QA, RAG"
    ),
    # Safety
    Agent(
        name="TextAttack",
        description="A framework for adversarial attacks, data augmentation and adversarial training in NLP.",
        category="Safety",
        tech_stack=["Python", "PyTorch", "Transformers"],
        github_stars=3467,
        url="https://github.com/QData/TextAttack",
        use_case="Adversarial testing of text models"
    ),
    Agent(
        name="Foolbox",
        description="A library of adversarial attacks for finding the smallest perturbation that fools a model.",
        category="Safety",
        tech_stack=["Python", "PyTorch", "JAX"],
        github_stars=2972,
        url="https://github.com/bethgelab/foolbox",
        use_case="Finding the smallest perturbation that fools a model"
    ),
    Agent(
        name="Counterfit",
        description="A command line tool for assessing the security of machine learning systems.",
        category="Safety",
        tech_stack=["Python", "CLI"],
        github_stars=935,
        url="https://github.com/Azure/counterfit",
        use_case="Attacking a deployed ML service"
    ),
    Agent(
        name="Opacus",
        description="Trains PyTorch models with differential privacy, with little change to the training loop.",
        category="Safety",
        tech_stack=["Python", "PyTorch"],
        github_stars=1951,
        url="https://github.com/meta-pytorch/opacus",
        use_case="Differentially private training"
    ),
    Agent(
        name="Fairlearn",
        description="Assesses and mitigates unfairness in models, with metrics grouped by who is affected.",
        category="Safety",
        tech_stack=["Python", "scikit-learn"],
        github_stars=2268,
        url="https://github.com/fairlearn/fairlearn",
        use_case="Fairness metrics grouped by who is affected"
    ),
    Agent(
        name="AI Fairness 360",
        description="A toolkit of bias metrics and mitigation algorithms for datasets and models.",
        category="Safety",
        tech_stack=["Python", "R", "scikit-learn"],
        github_stars=2852,
        url="https://github.com/Trusted-AI/AIF360",
        use_case="A catalogue of bias mitigation algorithms"
    ),
    # Evaluation
    Agent(
        name="HELM",
        description="Stanford's holistic benchmark, scoring models on accuracy, calibration, bias and toxicity together.",
        category="Evaluation",
        tech_stack=["Python", "Transformers"],
        github_stars=2879,
        url="https://github.com/stanford-crfm/helm",
        use_case="Broad multi-metric model benchmarking"
    ),
    Agent(
        name="OpenAI Evals",
        description="A registry of benchmarks and a framework for writing your own against any model.",
        category="Evaluation",
        tech_stack=["Python", "YAML"],
        github_stars=19187,
        url="https://github.com/openai/evals",
        use_case="Writing and running custom evals"
    ),
    Agent(
        name="TruLens",
        description="Instruments LLM apps and scores each step with feedback functions for groundedness and relevance.",
        category="Evaluation",
        tech_stack=["Python", "LangChain", "LlamaIndex"],
        github_stars=3512,
        url="https://github.com/truera/trulens",
        use_case="Feedback functions over app traces"
    ),
    Agent(
        name="LightEval",
        description="A lightweight harness for evaluating models across several backends from one config.",
        category="Evaluation",
        tech_stack=["Python", "Transformers", "vLLM"],
        github_stars=2520,
        url="https://github.com/huggingface/lighteval",
        use_case="Fast multi-backend evaluation"
    ),
    Agent(
        name="Alibi Detect",
        description="Detects outliers, adversarial input and drift in production data, for text and images alike.",
        category="Evaluation",
        tech_stack=["Python", "TensorFlow", "PyTorch"],
        github_stars=2547,
        url="https://github.com/SeldonIO/alibi-detect",
        use_case="Drift and outlier detection"
    ),
    # Fine-tuning
    Agent(
        name="XTuner",
        description="An efficient toolkit for fine-tuning LLMs and vision-language models on limited hardware.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "DeepSpeed"],
        github_stars=5180,
        url="https://github.com/InternLM/xtuner",
        use_case="Memory-efficient LLM fine-tuning"
    ),
    Agent(
        name="TorchTitan",
        description="PyTorch's own reference for pretraining large models, showing each parallelism in plain code.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "FSDP"],
        github_stars=5633,
        url="https://github.com/pytorch/torchtitan",
        use_case="Large-scale distributed pretraining"
    ),
    Agent(
        name="verl",
        description="A reinforcement learning library for post-training LLMs, built for RLHF at scale.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "Ray", "vLLM"],
        github_stars=23003,
        url="https://github.com/verl-project/verl",
        use_case="RLHF and reasoning post-training"
    ),
    Agent(
        name="AutoTrain Advanced",
        description="Trains and fine-tunes models from a config file or web UI, without writing a training loop.",
        category="Fine-tuning",
        tech_stack=["Python", "Transformers", "PEFT"],
        github_stars=4604,
        url="https://github.com/huggingface/autotrain-advanced",
        use_case="No-code model fine-tuning"
    ),
    # Robotics
    Agent(
        name="ManiSkill",
        description="A GPU-parallelised simulator for robot manipulation, with hundreds of tasks and demonstrations.",
        category="Robotics",
        tech_stack=["Python", "SAPIEN", "PyTorch"],
        github_stars=3234,
        url="https://github.com/mani-skill/ManiSkill",
        use_case="Manipulation benchmarks and training"
    ),
    Agent(
        name="SAPIEN",
        description="A physics simulator built for articulated objects, so doors, drawers and tools behave.",
        category="Robotics",
        tech_stack=["C++", "Python", "PhysX"],
        github_stars=818,
        url="https://github.com/haosulab/SAPIEN",
        use_case="Articulated object simulation"
    ),
    Agent(
        name="CARLA",
        description="An open simulator for autonomous driving research, with configurable towns, traffic and weather.",
        category="Robotics",
        tech_stack=["C++", "Python", "Unreal Engine"],
        github_stars=14300,
        url="https://github.com/carla-simulator/carla",
        use_case="Self-driving simulation and testing"
    ),
    Agent(
        name="Rerun",
        description="A viewer for multimodal robot data: log point clouds, images and transforms and scrub through time.",
        category="Robotics",
        tech_stack=["Rust", "Python", "C++"],
        github_stars=11314,
        url="https://github.com/rerun-io/rerun",
        use_case="Visualising and debugging robot data"
    ),
    Agent(
        name="dora-rs",
        description="A low-latency dataflow runtime for robotics, wiring nodes together with shared memory.",
        category="Robotics",
        tech_stack=["Rust", "Python", "Arrow"],
        github_stars=3879,
        url="https://github.com/dora-rs/dora",
        use_case="Robot dataflow and middleware"
    ),
    Agent(
        name="MuJoCo Menagerie",
        description="A collection of high-quality MuJoCo models for real robots, tuned so simulation matches hardware.",
        category="Robotics",
        tech_stack=["MuJoCo", "XML", "Python"],
        github_stars=3830,
        url="https://github.com/google-deepmind/mujoco_menagerie",
        use_case="Ready-made robot models for simulation"
    ),
    # Customer Service
    Agent(
        name="Zammad",
        description="A help desk that pulls tickets from mail, chat and social into one timeline per customer.",
        category="Customer Service",
        tech_stack=["Ruby", "Rails", "Elasticsearch"],
        github_stars=5852,
        url="https://github.com/zammad/zammad",
        use_case="Self-hosted ticketing and help desk"
    ),
    Agent(
        name="FreeScout",
        description="A shared inbox and help desk that runs on ordinary PHP hosting.",
        category="Customer Service",
        tech_stack=["PHP", "Laravel", "MySQL"],
        github_stars=4482,
        url="https://github.com/freescout-help-desk/freescout",
        use_case="Shared inbox for support mail"
    ),
    Agent(
        name="erxes",
        description="An experience suite joining support, sales and marketing so one conversation carries across them.",
        category="Customer Service",
        tech_stack=["TypeScript", "React", "GraphQL"],
        github_stars=4066,
        url="https://github.com/erxes/erxes",
        use_case="Customer engagement across channels"
    ),
    # Autonomous Agent
    Agent(
        name="UI-TARS Desktop",
        description="A desktop app that drives your computer and browser from natural language, using a vision-language model.",
        category="Autonomous Agent",
        tech_stack=["TypeScript", "Electron", "UI-TARS"],
        github_stars=38612,
        url="https://github.com/bytedance/UI-TARS-desktop",
        use_case="GUI automation from plain instructions"
    ),
    Agent(
        name="Agent-S",
        description="An agent framework for using a computer the way a person does, learning from its own past attempts.",
        category="Autonomous Agent",
        tech_stack=["Python", "GPT-4", "Claude"],
        github_stars=12164,
        url="https://github.com/simular-ai/Agent-S",
        use_case="Computer use with experience reuse"
    ),
    Agent(
        name="Rowboat",
        description="Builds and runs multi-agent workflows from a description, with the agents visible as a graph.",
        category="Autonomous Agent",
        tech_stack=["TypeScript", "Next.js", "MCP"],
        github_stars=17305,
        url="https://github.com/rowboatlabs/rowboat",
        use_case="Assembling multi-agent workflows"
    ),
    Agent(
        name="Upsonic",
        description="An agent framework built around reliability, with verification passes over each task's output.",
        category="Autonomous Agent",
        tech_stack=["Python", "Pydantic", "MCP"],
        github_stars=7941,
        url="https://github.com/Upsonic/Upsonic",
        use_case="Agents with verified outputs"
    ),
    Agent(
        name="PocketFlow",
        description="A minimal agent framework in a hundred lines, expressing everything as a graph of nodes.",
        category="Framework",
        tech_stack=["Python"],
        github_stars=11108,
        url="https://github.com/The-Pocket/PocketFlow",
        use_case="Minimal dependency-free agent graphs"
    ),
    Agent(
        name="BeeAI Framework",
        description="IBM's framework for production agents, with the same workflows available in Python and TypeScript.",
        category="Framework",
        tech_stack=["Python", "TypeScript", "MCP"],
        github_stars=3380,
        url="https://github.com/i-am-bee/beeai-framework",
        use_case="Production agents in two languages"
    ),
    # Automation
    Agent(
        name="Apache Airflow",
        description="Schedules and monitors data pipelines defined as Python DAGs, with retries, backfills and dependency handling built in.",
        category="Automation",
        tech_stack=["Python", "Celery", "Kubernetes"],
        github_stars=46521,
        url="https://github.com/apache/airflow",
        use_case="Scheduling data and ML pipelines"
    ),
    Agent(
        name="Prefect",
        description="Turns ordinary Python functions into observable workflows, with state and retries added by decorator.",
        category="Automation",
        tech_stack=["Python", "Pydantic"],
        github_stars=23634,
        url="https://github.com/PrefectHQ/prefect",
        use_case="Orchestrating Python workflows"
    ),
    Agent(
        name="Temporal",
        description="Runs long-lived workflows durably: a process survives a crash and resumes where it stopped.",
        category="Automation",
        tech_stack=["Go", "Java", "TypeScript"],
        github_stars=22387,
        url="https://github.com/temporalio/temporal",
        use_case="Durable long-running workflows"
    ),
    Agent(
        name="Conductor",
        description="Orchestrates microservices as a workflow defined in JSON, with each step visible while it runs.",
        category="Automation",
        tech_stack=["Java", "Spring", "Redis"],
        github_stars=32101,
        url="https://github.com/conductor-oss/conductor",
        use_case="Microservice workflow orchestration"
    ),
    Agent(
        name="Trigger.dev",
        description="Background jobs and AI workflows for TypeScript, written in your own codebase and run elsewhere.",
        category="Automation",
        tech_stack=["TypeScript", "Next.js", "PostgreSQL"],
        github_stars=16056,
        url="https://github.com/triggerdotdev/trigger.dev",
        use_case="Long-running background jobs"
    ),
    Agent(
        name="ToolJet",
        description="Builds internal tools and AI agents from a drag-and-drop canvas wired to your own databases and APIs.",
        category="Automation",
        tech_stack=["JavaScript", "React", "NestJS"],
        github_stars=40433,
        url="https://github.com/ToolJet/ToolJet",
        use_case="Low-code internal tools"
    ),
    Agent(
        name="Budibase",
        description="Builds internal apps and automations over existing data without writing the front end.",
        category="Automation",
        tech_stack=["TypeScript", "Svelte", "CouchDB"],
        github_stars=28216,
        url="https://github.com/Budibase/budibase",
        use_case="Internal apps over existing data"
    ),
    # MLOps
    Agent(
        name="SkyPilot",
        description="Runs training and serving jobs on whichever cloud has capacity, and moves them when it is cheaper elsewhere.",
        category="MLOps",
        tech_stack=["Python", "Kubernetes", "Ray"],
        github_stars=10505,
        url="https://github.com/skypilot-org/skypilot",
        use_case="Running jobs across clouds"
    ),
    Agent(
        name="KServe",
        description="Serves models on Kubernetes with autoscaling to zero, canary rollout and a common prediction interface.",
        category="MLOps",
        tech_stack=["Go", "Kubernetes", "Knative"],
        github_stars=5801,
        url="https://github.com/kserve/kserve",
        use_case="Serving models on Kubernetes"
    ),
    Agent(
        name="Seldon Core",
        description="Deploys models as inference graphs, so pre-processing, the model and an explainer are one deployment.",
        category="MLOps",
        tech_stack=["Go", "Python", "Kubernetes"],
        github_stars=4773,
        url="https://github.com/SeldonIO/seldon-core",
        use_case="Model deployment and inference graphs"
    ),
    Agent(
        name="Mage",
        description="Builds and schedules data pipelines from notebook-style blocks that each stay independently runnable.",
        category="MLOps",
        tech_stack=["Python", "React", "Docker"],
        github_stars=8804,
        url="https://github.com/mage-ai/mage-ai",
        use_case="Building and scheduling data pipelines"
    ),
    Agent(
        name="Polyaxon",
        description="Tracks experiments and schedules distributed training on Kubernetes, keeping every run reproducible.",
        category="MLOps",
        tech_stack=["Python", "Kubernetes", "Docker"],
        github_stars=3719,
        url="https://github.com/polyaxon/polyaxon",
        use_case="Experiment tracking and orchestration"
    ),
    # Customer Service
    Agent(
        name="MaxKB",
        description="Builds agents that answer from a company's own knowledge base, with the retrieval and the chat UI included.",
        category="Customer Service",
        tech_stack=["Python", "Vue.js", "LangChain"],
        github_stars=22542,
        url="https://github.com/1Panel-dev/MaxKB",
        use_case="Knowledge base question answering"
    ),
    Agent(
        name="AstrBot",
        description="One assistant reachable from Discord, Telegram, WeChat and QQ at once, extended through plugins.",
        category="Customer Service",
        tech_stack=["Python", "Docker"],
        github_stars=39332,
        url="https://github.com/AstrBotDevs/AstrBot",
        use_case="One bot across messaging platforms"
    ),
    Agent(
        name="ChatterBot",
        description="A dialog engine that learns replies from example conversations, with no model provider involved.",
        category="Customer Service",
        tech_stack=["Python", "SQLAlchemy"],
        github_stars=14510,
        url="https://github.com/gunthercox/ChatterBot",
        use_case="Rule and corpus based chat bots"
    ),
    Agent(
        name="Frappe Helpdesk",
        description="Customer support ticketing with a knowledge base and canned replies, self-hosted end to end.",
        category="Customer Service",
        tech_stack=["Python", "Vue.js", "Frappe"],
        github_stars=3319,
        url="https://github.com/frappe/helpdesk",
        use_case="Support ticketing and knowledge base"
    ),
    # Fine-tuning
    Agent(
        name="Colossal-AI",
        description="Trains models too large for one GPU by combining tensor, pipeline and sequence parallelism behind a small API.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "CUDA"],
        github_stars=41437,
        url="https://github.com/hpcaitech/ColossalAI",
        use_case="Large-scale parallel training"
    ),
    Agent(
        name="PyTorch Lightning",
        description="Takes the training loop, checkpointing and multi-GPU wiring off you while leaving the model plain PyTorch.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch"],
        github_stars=31292,
        url="https://github.com/Lightning-AI/pytorch-lightning",
        use_case="Structuring and scaling training code"
    ),
    Agent(
        name="LMFlow",
        description="Fine-tunes and serves large foundation models from one toolkit, aimed at teams without a cluster.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "DeepSpeed"],
        github_stars=8485,
        url="https://github.com/OptimalScale/LMFlow",
        use_case="Fine-tuning foundation models"
    ),
    Agent(
        name="GPT-NeoX",
        description="EleutherAI's library for training large autoregressive language models across many GPUs.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "DeepSpeed"],
        github_stars=7453,
        url="https://github.com/EleutherAI/gpt-neox",
        use_case="Training large language models"
    ),
    Agent(
        name="Composer",
        description="Speeds up training with a library of algorithmic methods that can be switched on individually.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch"],
        github_stars=5495,
        url="https://github.com/mosaicml/composer",
        use_case="Faster training through algorithms"
    ),
    # Evaluation and Safety
    Agent(
        name="SWE-bench",
        description="Benchmarks coding agents on real GitHub issues, scored by whether the repository's own tests pass afterwards.",
        category="Evaluation",
        tech_stack=["Python", "Docker"],
        github_stars=5663,
        url="https://github.com/SWE-bench/SWE-bench",
        use_case="Benchmarking coding agents on real bugs"
    ),
    Agent(
        name="MTEB",
        description="Ranks text embedding models across retrieval, clustering and classification, so one leaderboard covers the trade-offs.",
        category="Evaluation",
        tech_stack=["Python", "Sentence Transformers"],
        github_stars=3397,
        url="https://github.com/embeddings-benchmark/mteb",
        use_case="Comparing embedding models"
    ),
    Agent(
        name="DeepTeam",
        description="Red teams an LLM application against a catalogue of vulnerabilities, generating the attacks rather than listing them.",
        category="Safety",
        tech_stack=["Python", "DeepEval"],
        github_stars=2503,
        url="https://github.com/confident-ai/deepteam",
        use_case="Red teaming an LLM application"
    ),
    Agent(
        name="AgentDojo",
        description="Puts an agent in a sandboxed environment and measures whether injected instructions in its tool output can hijack it.",
        category="Safety",
        tech_stack=["Python"],
        github_stars=756,
        url="https://github.com/ethz-spylab/agentdojo",
        use_case="Benchmarking an agent against injected instructions"
    ),
    # Research
    Agent(
        name="STORM",
        description="Researches a topic by simulating expert interviews, then writes a cited Wikipedia-style article from what it found.",
        category="Research",
        tech_stack=["Python", "DSPy"],
        github_stars=31072,
        url="https://github.com/stanford-oval/storm",
        use_case="Writing a cited article from research"
    ),
    Agent(
        name="Vane",
        description="An open answer engine that searches the web and cites its sources, formerly released as Perplexica.",
        category="Research",
        tech_stack=["TypeScript", "Next.js", "SearXNG"],
        github_stars=36252,
        url="https://github.com/ItzCrazyKns/Vane",
        use_case="Self-hosted web answer engine"
    ),
    Agent(
        name="R2R",
        description="A retrieval engine with ingestion, hybrid search and knowledge graphs behind one REST API.",
        category="Research",
        tech_stack=["Python", "PostgreSQL", "FastAPI"],
        github_stars=7974,
        url="https://github.com/SciPhi-AI/R2R",
        use_case="Retrieval behind a REST API"
    ),
    Agent(
        name="Morphic",
        description="A search interface that streams an answer alongside the sources and follow-up questions it suggests.",
        category="Research",
        tech_stack=["TypeScript", "Next.js", "Vercel AI SDK"],
        github_stars=9048,
        url="https://github.com/miurla/morphic",
        use_case="Generative answers with follow-ups"
    ),
    Agent(
        name="AI Scientist",
        description="Runs a research loop end to end: proposes ideas, runs experiments, writes the paper and reviews it.",
        category="Research",
        tech_stack=["Python", "PyTorch", "LaTeX"],
        github_stars=14425,
        url="https://github.com/SakanaAI/AI-Scientist",
        use_case="Automating a research cycle"
    ),
    # Autonomous Agent
    Agent(
        name="OWL",
        description="A multi-agent framework built on CAMEL where agents divide a task and hand work between them.",
        category="Autonomous Agent",
        tech_stack=["Python", "CAMEL", "MCP"],
        github_stars=20086,
        url="https://github.com/camel-ai/owl",
        use_case="Dividing a task between agents"
    ),
    Agent(
        name="Cua",
        description="Gives an agent a sandboxed macOS or Linux virtual machine to work in, so it cannot touch the host.",
        category="Autonomous Agent",
        tech_stack=["Python", "Swift", "Docker"],
        github_stars=21579,
        url="https://github.com/trycua/cua",
        use_case="Computer use inside a sandbox"
    ),
    Agent(
        name="Nanobrowser",
        description="A Chrome extension that drives your own browser session, keeping cookies and logins already there.",
        category="Autonomous Agent",
        tech_stack=["TypeScript", "Chrome Extension"],
        github_stars=13575,
        url="https://github.com/nanobrowser/nanobrowser",
        use_case="Browser tasks in your own session"
    ),
    # Robotics
    Agent(
        name="Bullet",
        description="The physics engine behind PyBullet, widely used for reinforcement learning because it is fast and free.",
        category="Robotics",
        tech_stack=["C++", "Python", "PyBullet"],
        github_stars=14683,
        url="https://github.com/bulletphysics/bullet3",
        use_case="Physics for reinforcement learning"
    ),
    Agent(
        name="Webots",
        description="A robot simulator with a large library of ready-made robots, sensors and worlds to drop them into.",
        category="Robotics",
        tech_stack=["C++", "Python", "ROS 2"],
        github_stars=4563,
        url="https://github.com/cyberbotics/webots",
        use_case="Simulating a robot in a prebuilt world"
    ),
    Agent(
        name="Gazebo",
        description="The simulator ROS grew up with, now rebuilt as separate libraries you can use without the rest.",
        category="Robotics",
        tech_stack=["C++", "ROS 2", "OGRE"],
        github_stars=1451,
        url="https://github.com/gazebosim/gz-sim",
        use_case="Simulation alongside ROS"
    ),
    Agent(
        name="Open3D",
        description="Processes point clouds and meshes — registration, reconstruction and visualisation — from Python or C++.",
        category="Robotics",
        tech_stack=["C++", "Python", "CUDA"],
        github_stars=13897,
        url="https://github.com/isl-org/Open3D",
        use_case="Working with point clouds and meshes"
    ),
    Agent(
        name="PX4",
        description="Flight control software for drones and other autonomous vehicles, running on real airframes.",
        category="Robotics",
        tech_stack=["C++", "NuttX", "MAVLink"],
        github_stars=12449,
        url="https://github.com/PX4/PX4-Autopilot",
        use_case="Flight control for autonomous vehicles"
    ),
    Agent(
        name="cuRobo",
        description="NVIDIA's GPU motion planner, solving inverse kinematics and collision-free trajectories in milliseconds.",
        category="Robotics",
        tech_stack=["Python", "CUDA", "PyTorch"],
        github_stars=1779,
        url="https://github.com/NVlabs/curobo",
        use_case="Fast motion planning on a GPU"
    ),
    # Customer Service
    Agent(
        name="Ultravox",
        description="A speech language model that listens and answers directly, without transcribing to text and back again.",
        category="Customer Service",
        tech_stack=["Python", "PyTorch", "Llama"],
        github_stars=4546,
        url="https://github.com/fixie-ai/ultravox",
        use_case="Real-time voice conversation"
    ),
    Agent(
        name="osTicket",
        description="Routes support email and web forms into queues with SLAs, canned replies and per-department rules.",
        category="Customer Service",
        tech_stack=["PHP", "MySQL"],
        github_stars=3893,
        url="https://github.com/osTicket/osTicket",
        use_case="Routing support email into queues"
    ),
    Agent(
        name="Twenty",
        description="An open CRM that keeps the record of every customer, deal and conversation on your own infrastructure.",
        category="Customer Service",
        tech_stack=["TypeScript", "NestJS", "PostgreSQL"],
        github_stars=55128,
        url="https://github.com/twentyhq/twenty",
        use_case="Tracking customers and deals"
    ),
    Agent(
        name="Rocket.Chat",
        description="Team messaging with an omnichannel desk, so a customer on WhatsApp lands in the same place as internal chat.",
        category="Customer Service",
        tech_stack=["TypeScript", "MongoDB", "Meteor"],
        github_stars=46005,
        url="https://github.com/RocketChat/Rocket.Chat",
        use_case="Self-hosted team and customer chat"
    ),
    # Code Generation
    Agent(
        name="Codex CLI",
        description="OpenAI's coding agent for the terminal, running against your checkout inside a configurable sandbox.",
        category="Code Generation",
        tech_stack=["Rust", "TypeScript"],
        github_stars=107085,
        url="https://github.com/openai/codex",
        use_case="Sandboxed coding tasks in the terminal"
    ),
    Agent(
        name="Crush",
        description="A terminal coding agent that reads your project through its language server and switches model mid-session.",
        category="Code Generation",
        tech_stack=["Go", "LSP", "MCP"],
        github_stars=27523,
        url="https://github.com/charmbracelet/crush",
        use_case="Coding with language server context"
    ),
    Agent(
        name="PR-Agent",
        description="Answers slash commands on a pull request — describe it, review it, suggest improvements — from the thread itself.",
        category="Code Generation",
        tech_stack=["Python", "GitHub Actions"],
        github_stars=12633,
        url="https://github.com/The-PR-Agent/pr-agent",
        use_case="Slash commands on a pull request"
    ),
    # MLOps
    Agent(
        name="Feast",
        description="A feature store that serves the same feature definitions to training and to production, so the two cannot drift.",
        category="MLOps",
        tech_stack=["Python", "Redis", "BigQuery"],
        github_stars=7223,
        url="https://github.com/feast-dev/feast",
        use_case="Sharing features between training and serving"
    ),
    Agent(
        name="Triton Inference Server",
        description="NVIDIA's server for running models from any framework on one GPU fleet, with batching and concurrent execution.",
        category="MLOps",
        tech_stack=["C++", "Python", "CUDA"],
        github_stars=10926,
        url="https://github.com/triton-inference-server/server",
        use_case="High-throughput GPU inference"
    ),
    Agent(
        name="LocalAI",
        description="Serves local models behind the OpenAI API, so existing clients point at your hardware without code changes.",
        category="MLOps",
        tech_stack=["Go", "llama.cpp", "Docker"],
        github_stars=48597,
        url="https://github.com/mudler/LocalAI",
        use_case="An OpenAI-shaped API over local models"
    ),
    Agent(
        name="Xinference",
        description="Runs and scales language, embedding and image models across a cluster from one registry.",
        category="MLOps",
        tech_stack=["Python", "vLLM", "Ray"],
        github_stars=9502,
        url="https://github.com/xorbitsai/inference",
        use_case="Serving many model types from one cluster"
    ),
    # Evaluation
    Agent(
        name="Helicone",
        description="A proxy in front of the model that logs every call, its cost and its latency, without touching the application.",
        category="Evaluation",
        tech_stack=["TypeScript", "PostgreSQL", "ClickHouse"],
        github_stars=6087,
        url="https://github.com/Helicone/helicone",
        use_case="Logging model calls through a proxy"
    ),
    Agent(
        name="Weave",
        description="Weights & Biases' toolkit for LLM apps: capture every call as a trace and score it against a saved dataset.",
        category="Evaluation",
        tech_stack=["Python", "TypeScript"],
        github_stars=1121,
        url="https://github.com/wandb/weave",
        use_case="Scoring traces against a dataset"
    ),
    Agent(
        name="Langtrace",
        description="OpenTelemetry-native tracing for agents and RAG, so LLM spans land in the observability stack you already run.",
        category="Evaluation",
        tech_stack=["TypeScript", "OpenTelemetry", "Python"],
        github_stars=1228,
        url="https://github.com/Scale3-Labs/langtrace",
        use_case="LLM spans in an existing observability stack"
    ),
    # Data Analysis
    Agent(
        name="D-Tale",
        description="Opens a pandas dataframe in a browser where you can sort, filter, chart and describe it without writing code.",
        category="Data Analysis",
        tech_stack=["Python", "TypeScript", "React", "Flask"],
        github_stars=5215,
        url="https://github.com/man-group/dtale",
        use_case="Inspecting a dataframe in a browser"
    ),
    Agent(
        name="fg-data-profiling",
        description="One line turns a dataframe into an HTML report of distributions, correlations and missing values; formerly ydata-profiling.",
        category="Data Analysis",
        tech_stack=["Python", "Pandas", "Jupyter"],
        github_stars=13679,
        url="https://github.com/Data-Centric-AI-Community/fg-data-profiling",
        use_case="A one-call report on a dataset"
    ),
    Agent(
        name="Soda Core",
        description="Checks data against expectations written in a readable YAML dialect and fails the pipeline when they break.",
        category="Data Analysis",
        tech_stack=["Python", "SQL", "YAML"],
        github_stars=2413,
        url="https://github.com/sodadata/soda-core",
        use_case="Data checks written in plain YAML"
    ),
    # Multimodal
    Agent(
        name="SAM 2",
        description="Segments any object in an image or video from a click, and tracks it across frames.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch"],
        github_stars=19737,
        url="https://github.com/facebookresearch/sam2",
        use_case="Segmenting and tracking objects"
    ),
    Agent(
        name="Open-Sora",
        description="Generates video from a text prompt, with the training recipe and weights published rather than held back.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch", "Diffusers"],
        github_stars=29281,
        url="https://github.com/hpcaitech/Open-Sora",
        use_case="Generating video from text"
    ),
    Agent(
        name="Moshi",
        description="A speech model that listens and talks at the same time, so it can be interrupted mid-sentence.",
        category="Multimodal",
        tech_stack=["Python", "Rust", "PyTorch"],
        github_stars=10915,
        url="https://github.com/kyutai-labs/moshi",
        use_case="Full-duplex spoken dialogue"
    ),
    Agent(
        name="MiniCPM-V",
        description="A vision-language model small enough to run on a phone while still reading documents and video.",
        category="Multimodal",
        tech_stack=["Python", "PyTorch", "llama.cpp"],
        github_stars=26210,
        url="https://github.com/OpenBMB/MiniCPM-V",
        use_case="Vision-language on a phone"
    ),
    # Safety
    Agent(
        name="agent-scan",
        description="Scans the MCP servers an agent is wired to, flagging tool descriptions that try to redirect it.",
        category="Safety",
        tech_stack=["Python", "MCP"],
        github_stars=2936,
        url="https://github.com/snyk/agent-scan",
        use_case="Auditing the tools an agent trusts"
    ),
    Agent(
        name="Agentic Radar",
        description="Maps an agent workflow into a diagram and marks where a prompt or a tool could take it off course.",
        category="Safety",
        tech_stack=["Python", "LangGraph", "CrewAI"],
        github_stars=1039,
        url="https://github.com/splx-ai/agentic-radar",
        use_case="Mapping the risk surface of a workflow"
    ),
    # Document handling
    Agent(
        name="MinerU",
        description="Converts a PDF to machine-readable text, keeping reading order, tables and formulas intact.",
        category="Framework",
        tech_stack=["Python", "PyTorch", "PaddleOCR"],
        github_stars=78153,
        url="https://github.com/opendatalab/MinerU",
        use_case="PDF to structured text"
    ),
    Agent(
        name="Marker",
        description="Turns PDFs, EPUBs and slides into clean markdown quickly, using models only where the layout needs them.",
        category="Framework",
        tech_stack=["Python", "PyTorch", "Surya"],
        github_stars=38948,
        url="https://github.com/datalab-to/marker",
        use_case="Documents to markdown"
    ),
    Agent(
        name="Unstract",
        description="Defines what to pull out of a document once, then runs it over every file as an API.",
        category="Automation",
        tech_stack=["Python", "Django", "PostgreSQL"],
        github_stars=7156,
        url="https://github.com/Zipstack/unstract",
        use_case="Structured extraction as an API"
    ),
    # Found by the crawler
    Agent(
        name="Strix",
        description="Runs agents against your own application the way an attacker would, then reports what they got through.",
        category="Safety",
        tech_stack=["Python", "Docker"],
        github_stars=57649,
        url="https://github.com/usestrix/strix",
        use_case="Penetration testing by agent"
    ),
    Agent(
        name="Daytona",
        description="Gives agent-written code a disposable machine to run on, started in under a second and thrown away after.",
        category="Infrastructure",
        tech_stack=["Go", "TypeScript", "Docker"],
        github_stars=71891,
        url="https://github.com/daytonaio/daytona",
        use_case="Disposable runtimes for generated code"
    ),
    Agent(
        name="Graphiti",
        description="Builds a temporal knowledge graph from an agent's conversations, so a fact can change without the old one being lost.",
        category="Infrastructure",
        tech_stack=["Python", "Neo4j"],
        github_stars=30256,
        url="https://github.com/getzep/graphiti",
        use_case="Knowledge graph memory over time"
    ),
    Agent(
        name="Rig",
        description="Builds LLM applications in Rust, with typed completions and vector stores behind one set of traits.",
        category="Framework",
        tech_stack=["Rust"],
        github_stars=8387,
        url="https://github.com/0xPlaygrounds/rig",
        use_case="Typed LLM applications in Rust"
    ),
    Agent(
        name="TradingAgents",
        description="Models a trading desk as separate agents \u2014 analyst, researcher, trader, risk \u2014 that argue before a position is taken.",
        category="Autonomous Agent",
        tech_stack=["Python", "LangGraph"],
        github_stars=99671,
        url="https://github.com/TauricResearch/TradingAgents",
        use_case="Agents debating a trade"
    ),
    Agent(
        name="Bifrost",
        description="An LLM gateway in Go that fails over between providers and keeps the same API when one goes down.",
        category="MLOps",
        tech_stack=["Go", "Redis"],
        github_stars=7538,
        url="https://github.com/maximhq/bifrost",
        use_case="Failing over between providers"
    ),
    # Found by the crawler
    Agent(
        name="Oumi",
        description="Covers the whole path from data preparation to fine-tuning to evaluation with one configuration file.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "vLLM"],
        github_stars=9376,
        url="https://github.com/oumi-ai/oumi",
        use_case="One config from data to evaluation"
    ),
    Agent(
        name="Kiln",
        description="A desktop app for building datasets, fine-tuning and comparing the results without writing training code.",
        category="Fine-tuning",
        tech_stack=["Python", "TypeScript", "Svelte"],
        github_stars=5034,
        url="https://github.com/Kiln-AI/Kiln",
        use_case="Fine-tuning from a desktop app"
    ),
    Agent(
        name="H2O LLM Studio",
        description="A web interface for fine-tuning language models, with the hyperparameters exposed as form fields.",
        category="Fine-tuning",
        tech_stack=["Python", "PyTorch", "Wave"],
        github_stars=5173,
        url="https://github.com/h2oai/h2o-llmstudio",
        use_case="Fine-tuning through a web form"
    ),
    Agent(
        name="OpenCompass",
        description="Runs a model against a hundred-plus benchmarks and publishes the leaderboard the numbers came from.",
        category="Evaluation",
        tech_stack=["Python", "PyTorch"],
        github_stars=7333,
        url="https://github.com/open-compass/opencompass",
        use_case="Benchmarking across many datasets"
    ),
    Agent(
        name="VLMEvalKit",
        description="Evaluates vision-language models on twenty-plus multimodal benchmarks from one command.",
        category="Evaluation",
        tech_stack=["Python", "PyTorch", "Transformers"],
        github_stars=4356,
        url="https://github.com/open-compass/VLMEvalKit",
        use_case="Benchmarking vision-language models"
    ),
    Agent(
        name="ChainForge",
        description="Compares prompts and models side by side on a canvas, scoring the responses as the graph runs.",
        category="Evaluation",
        tech_stack=["TypeScript", "React", "Python"],
        github_stars=3027,
        url="https://github.com/ianarawjo/ChainForge",
        use_case="Comparing prompts on a canvas"
    ),
    Agent(
        name="LoRAX",
        description="Serves hundreds of LoRA adapters from a single base model on one GPU, swapping them per request.",
        category="Infrastructure",
        tech_stack=["Python", "Rust", "CUDA"],
        github_stars=3827,
        url="https://github.com/predibase/lorax",
        use_case="Many adapters on one GPU"
    ),
    Agent(
        name="Semantic Router",
        description="Decides which model or tool a request should go to from its embedding, before any generation happens.",
        category="Infrastructure",
        tech_stack=["Go", "Rust", "Envoy"],
        github_stars=5258,
        url="https://github.com/vllm-project/semantic-router",
        use_case="Routing a request by meaning"
    ),
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


def _for_file(agent: Agent) -> dict:
    """One record as it should appear on disk.

    Shared with the editor via admin.for_file, so the two writers cannot
    disagree about the format — they did, and a save followed by a re-seed
    rewrote 204 records for no reason.
    """
    from admin import for_file

    return for_file(agent.to_dict())


def write_agents_json(agents: list[Agent]) -> None:
    """Persist the catalogue back to data/agents.json."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.AGENTS_JSON, 'w') as f:
        json.dump([_for_file(agent) for agent in agents], f, indent=2)
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
    # The live suite asserts which agents surface for a set of known queries.
    # A new agent can displace an expected one, and `make check` does not run
    # those tests, so the failure would only appear in CI.
    logger.info("Run `make test-live` to check the retrieval guards still hold.")

if __name__ == "__main__":
    import sys

    from logging_setup import configure

    configure()
    try:
        seed_data()
    except CatalogueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
