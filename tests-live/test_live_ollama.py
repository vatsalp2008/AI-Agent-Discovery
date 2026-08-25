"""End-to-end tests against a real Ollama server.

The rest of the suite stubs langchain and Ollama so it runs anywhere in
milliseconds. That is the right default, but it cannot catch problems that
only appear against real models: wrong distance semantics, a prompt the chat
model ignores, or a timeout that is too tight.

These are skipped unless the pieces are actually present, so `make check`
behaves the same as before. Run them deliberately with:

    ollama pull nomic-embed-text
    ollama pull llama3.2
    pip install -r ai-agent-discovery/requirements.txt
    python ai-agent-discovery/seed.py
    make test-live

They live outside tests/ because they load the real langchain stack, which
tests/conftest.py replaces with stubs.
"""

import math
import os
import urllib.error
import urllib.request

import pytest

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Generation is sampled, so grounding is checked over several draws: a single
# stray sample is noise, a majority failure is a regression.
GROUNDING_SAMPLES = 3
GROUNDING_REQUIRED = 2


def _ollama_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as response:
            import json
            return {m["name"].split(":")[0] for m in json.load(response).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return set()


AVAILABLE = _ollama_models()

needs_embeddings = pytest.mark.skipif(
    "nomic-embed-text" not in AVAILABLE,
    reason="requires Ollama with nomic-embed-text pulled",
)
needs_chat = pytest.mark.skipif(
    "llama3.2" not in AVAILABLE,
    reason="requires Ollama with llama3.2 pulled",
)


@pytest.fixture(scope="module")
def live_store():
    """The real VectorStore over the real index."""
    pytest.importorskip("faiss", reason="requires faiss-cpu")
    pytest.importorskip("langchain_ollama", reason="requires langchain-ollama")

    import config
    from vectorstore import VectorStore

    if not os.path.exists(os.path.join(str(config.FAISS_DIR), "index.faiss")):
        pytest.skip("no seeded index; run seed.py first")

    store = VectorStore()
    if not store.vector_store:
        pytest.skip("index could not be loaded")
    return store


@needs_embeddings
def test_embeddings_are_unit_vectors():
    """scoring.relevance_score treats distance as cosine; that needs unit norms."""
    from embeddings import get_embeddings

    vector = get_embeddings().embed_query("a command line coding tool")
    norm = math.sqrt(sum(x * x for x in vector))
    assert norm == pytest.approx(1.0, abs=1e-3)


@needs_embeddings
def test_verbatim_description_finds_its_own_agent(live_store):
    results = live_store.search(
        "A command line tool that lets you pair program with GPT-3.5/4. "
        "Edits code in your local git repo.",
        limit=3,
    )
    assert results[0]["name"] == "Aider"
    assert results[0]["score"] > 0.85, "a verbatim match should score very high"


@needs_embeddings
def test_semantic_match_beats_keyword_overlap(live_store):
    """The query shares no words with the description it should match."""
    results = live_store.search("edit code from my shell without leaving it", limit=5)
    assert "Aider" in [r["name"] for r in results[:3]]


@needs_embeddings
def test_unrelated_query_scores_far_below_a_real_match(live_store):
    relevant = live_store.search("automate workflows between apps", limit=1)[0]
    nonsense = live_store.search("banana bread recipe", limit=1)[0]
    assert relevant["score"] - nonsense["score"] > 0.25, (
        "scores must separate relevant from irrelevant results"
    )


@needs_embeddings
def test_category_filter_holds_against_real_embeddings(live_store):
    results = live_store.search("agent", limit=5, category="Research")
    assert results
    assert {r["metadata"]["category"] for r in results} == {"Research"}


@needs_chat
@needs_embeddings
def test_generated_overview_is_grounded_in_the_results(live_store):
    """The prompt tells the model to use only the retrieved agents."""
    import generation

    query = "I need an agent that edits code in my terminal"
    results = live_store.search(query, limit=5)
    summary = generation.summarize(query, results)

    assert summary, "generation returned nothing against a real chat model"
    assert len(summary) > 40
    # It should name something it was actually given.
    assert any(r["name"].lower() in summary.lower() for r in results)


@needs_chat
@needs_embeddings
def test_generation_finishes_well_inside_the_timeout(live_store):
    """Measured warm, after a discarded call to load the model.

    A cold call also pays a one-time weight load — about 3s on a laptop, but
    several times that on a CPU-only CI runner, where it can approach the
    timeout. Timing the cold path would conflate model loading with generation
    speed and make this test fail for a reason it is not about.

    The cold path is still exercised: the discarded warm-up call below has to
    succeed, and every other generation test runs against whatever state the
    server is in.
    """
    import time

    import config
    import generation

    query = "workflow automation"
    results = live_store.search(query, limit=5)

    assert generation.summarize(query, results), "cold generation failed outright"

    start = time.perf_counter()
    summary = generation.summarize(query, results)
    elapsed = time.perf_counter() - start

    assert summary
    assert elapsed < config.SUMMARY_TIMEOUT, (
        f"warm generation took {elapsed:.1f}s against a {config.SUMMARY_TIMEOUT}s timeout"
    )


@needs_embeddings
def test_index_sidecar_matches_the_configured_model(live_store):
    import config

    assert live_store._read_meta().get("embedding_model") == config.EMBEDDING_MODEL
    assert live_store.stale_model is None


@needs_chat
@needs_embeddings
@pytest.mark.parametrize("query", [
    "agent that edits code in my terminal",
    "chat with my documents privately",
    "multi agent orchestration framework",
])
def _ungrounded_names(summary, prompt, catalogue):
    """Catalogue names the summary uses that appear nowhere in the prompt.

    Compared against the prompt text rather than the retrieved names, because
    some catalogue agents are also other agents' dependencies: PrivateGPT's own
    tech stack lists LlamaIndex, which is itself an indexed agent. Describing
    PrivateGPT with PrivateGPT's own field is correct, so only a name absent
    from the whole prompt counts as invention.
    """
    import re

    return {
        name for name in catalogue
        if re.search(rf"\b{re.escape(name)}\b", summary)
        and not re.search(rf"\b{re.escape(name)}\b", prompt)
    }


@needs_chat
@needs_embeddings
@pytest.mark.parametrize("query", [
    "agent that edits code in my terminal",
    "chat with my documents privately",
    "multi agent orchestration framework",
])
def test_overview_stays_grounded_in_the_prompt(live_store, query):
    """Naming an agent absent from the prompt means the model invented it.

    Sampled rather than asserted once. Generation is probabilistic, so a lone
    stray sample is noise, not a regression — asserting on one draw made this
    test fail roughly one run in five and broke CI twice. Drawing
    GROUNDING_SAMPLES and requiring a majority detects a real degradation in
    grounding (the thing a prompt change would cause) without failing on a
    single unlucky sample.

    This deliberately does not catch a small drop in grounding quality; it
    catches the prompt losing its grip.
    """
    import config
    import generation

    results = live_store.search(query, limit=5)
    prompt = generation.build_prompt(query, results[: config.SUMMARY_MAX_RESULTS])
    catalogue = {a["name"] for a in live_store.get_all_agents()}

    failures = []
    for _ in range(GROUNDING_SAMPLES):
        summary = generation.summarize(query, results)
        assert summary, "generation returned nothing"
        invented = _ungrounded_names(summary, prompt, catalogue)
        if invented:
            failures.append((sorted(invented), summary))

    allowed = GROUNDING_SAMPLES - GROUNDING_REQUIRED
    assert len(failures) <= allowed, (
        f"{len(failures)}/{GROUNDING_SAMPLES} samples named agents absent from the prompt "
        f"(at most {allowed} tolerated):\n" +
        "\n".join(f"  {names}: {text}" for names, text in failures)
    )


@needs_embeddings
@pytest.mark.parametrize("query,expected", [
    ("agent that edits code in my terminal", {"Claude Code", "Aider", "Goose", "Cline"}),
    ("chat with my documents privately", {"PrivateGPT", "LocalGPT", "AnythingLLM", "Khoj"}),
    ("turn plain english into SQL", {"Vanna AI", "DB-GPT"}),
    ("give my agent long term memory", {"Mem0", "Letta"}),
    ("automate a browser", {"Browser Use", "Skyvern", "Stagehand"}),
    ("multi agent orchestration framework", {"CrewAI", "AutoGen", "LangGraph", "MetaGPT"}),
    # Categories added as the catalogue grew past 60.
    ("measure whether my RAG pipeline hallucinates", {"Ragas", "DeepEval", "Giskard", "Phoenix"}),
    ("trace and monitor my LLM app in production", {"Langfuse", "Opik", "OpenLLMetry", "Phoenix"}),
    ("stop prompt injection attacks", {"Rebuff", "Garak", "Guardrails", "NeMo Guardrails"}),
    ("redact personal data before sending to a model", {"Presidio", "Guardrails"}),
    ("store embeddings in postgres", {"pgvector", "Chroma", "Qdrant"}),
    ("run language models on my own machine", {"Ollama", "vLLM", "LocalGPT", "Tabby"}),
    # Categories added as the catalogue grew past 82.
    # Narrowed back at 303, once the cause was fixed rather than accommodated.
    # This case passed by 0.002 for weeks with Megatron-LM (multi-node) and
    # MLC LLM (inference) above every right answer, then broke, and was
    # widened to most of the category to keep it honest — which left it unable
    # to tell "one GPU" from "many". The real fault was that nothing in
    # Unsloth's or PEFT's entry said single-GPU, though that is the whole
    # reason both exist. Said plainly, they take the top two places at 0.788
    # and 0.761 against 0.621 for the nearest multi-GPU tool, so the case can
    # go back to asserting what it was written to assert.
    ("fine tune a model on one GPU",
     {"Unsloth", "PEFT", "LLaMA-Factory", "Axolotl", "XTuner"}),
    ("transcribe speech to text", {"Whisper", "Faster Whisper"}),
    ("generate images locally", {"Stable Diffusion WebUI", "ComfyUI"}),
    ("build a realtime voice agent", {"Pipecat", "LiveKit Agents", "Vocode"}),
    ("serve a model as a production API", {"BentoML", "Ray", "vLLM", "Portkey Gateway"}),
    # Categories added as the catalogue grew past 106.
    ("run a model on apple silicon", {"MLX", "MLC LLM", "llama.cpp"}),
    ("train a robot policy", {"LeRobot"}),
    ("answer questions about scientific papers", {"PaperQA", "Nougat", "GraphRAG"}),
    ("convert a PDF into text for my model", {"MarkItDown", "Docling", "Unstructured", "Nougat"}),
    ("build an agent flow without writing code", {"Langflow", "Flowise", "n8n", "Dify"}),
    ("simulate robot physics for training", {"MuJoCo", "Isaac Lab", "Habitat Lab"}),
    ("standard interface for reinforcement learning environments", {"Gymnasium"}),
    ("transcribe audio with speaker labels", {"WhisperX", "Whisper", "Faster Whisper"}),
    ("generate speech from text", {"Bark", "Parler TTS", "Coqui TTS"}),
    ("red team a model for safety", {"PyRIT", "Garak", "PurpleLlama"}),
    # XTuner added at 303: it takes rank 1 here and its whole description is
    # "on limited hardware", so leaving it out made the case pass at third by
    # 0.0116 while the best answer went uncounted.
    ("fine tune a model with limited memory",
     {"Unsloth", "Axolotl", "PEFT", "XTuner"}),
    ("orchestrate data pipelines", {"Dagster", "Metaflow", "Flyte", "ZenML"}),
    ("self hosted chat interface for local models", {"Open WebUI", "LibreChat", "LobeHub"}),
    ("sandbox for running generated code", {"E2B", "OpenInterpreter"}),
    ("automate a windows desktop application", {"UFO", "OpenAdapt"}),
    ("track machine learning experiments", {"MLflow", "Weights & Biases", "Metaflow"}),
    # The thin categories filled out past 162. Each of these had no good
    # answer before, so they are the cases most likely to drift back.
    ("plan robot arm motion in ROS", {"MoveIt 2", "Nav2"}),
    ("rlhf and dpo alignment training", {"OpenRLHF", "TRL"}),
    ("train a model too large for one gpu", {"Megatron-LM", "OpenRLHF"}),
    ("ask questions about my database in plain english", {"Chat2DB", "Vanna AI", "DB-GPT"}),
    ("explore a dataframe visually in a notebook", {"PyGWalker", "Jupyter AI", "Sketch"}),
    # Expected widened at 278: H2O-3 takes rank 1 and PyCaret and FLAML are
    # equally AutoML, so the pair was narrower than the question. The margin
    # over the first wrong answer — Tabby, a coding assistant — was 0.0199.
    ("automated machine learning on tabular data",
     {"AutoGluon", "SDV", "H2O-3", "PyCaret", "FLAML"}),
    ("scan a model file for malicious code", {"ModelScan", "Garak"}),
    ("block prompt injection and pii in model output", {"LLM Guard", "Rebuff", "Presidio", "Guardrails"}),
    ("self hosted customer support helpdesk", {"Chaskiq", "Chatwoot"}),
    ("score text for toxicity", {"Detoxify", "LLM Guard"}),
    # Added at 203, filling out Evaluation, MLOps and Autonomous Agent.
    ("read text out of a scanned document", {"PaddleOCR", "Nougat"}),
    ("clone a voice from a short sample", {"GPT-SoVITS", "IndexTTS", "Coqui TTS"}),
    ("give an agent memory between conversations", {"cognee", "Mem0", "Letta"}),
    ("connect an agent to saas tools", {"Composio", "Zapier AI Actions", "MCP Servers"}),
    ("benchmark a model on standard tasks", {"LM Evaluation Harness", "Inspect AI", "DeepEval"}),
    ("typed versioned machine learning pipelines", {"Flyte", "Dagster", "Metaflow", "ZenML"}),
    ("self driving car software", {"openpilot"}),
    ("knowledge graph retrieval over documents", {"LightRAG", "GraphRAG"}),
    ("autonomous assistant that needs no api key", {"AgenticSeek", "LocalGPT", "PrivateGPT"}),
    ("analyse financial market text", {"FinGPT"}),
    ("typo tolerant search engine", {"Meilisearch"}),
    ("compare thousands of training runs", {"Aim", "Weights & Biases", "ClearML", "MLflow"}),
    # Added at 223, filling the thin categories again.
    ("label training data for a model", {"Label Studio", "Argilla"}),
    ("offline speech recognition on a small device", {"Vosk", "sherpa-onnx", "Faster Whisper"}),
    ("reinforcement learning baselines", {"Stable-Baselines3", "Gymnasium"}),
    ("build a web ui for a model", {"Gradio", "Taipy", "Open WebUI"}),
    ("agent framework for java", {"LangChain4j"}),
    ("answer questions from our company documents", {"Onyx", "AnythingLLM", "Quivr", "RAGFlow"}),
    ("record a repetitive browser task", {"Automa", "Maxun", "Browser Use", "OpenAdapt"}),
    ("structure a data science project", {"Kedro", "Metaflow", "ZenML"}),
    ("build a fine tuning dataset from documents", {"Easy Dataset", "Argilla"}),
    ("embeddings database with sql filtering", {"txtai", "LEANN", "Chroma"}),
    # Added at 236, from AI-specific data topics after "data-analysis"
    # returned pandas and superset.
    ("ask my warehouse a question in plain english", {"WrenAI", "Vanna AI", "Chat2DB", "SQLBot"}),
    ("automatically compare many machine learning models", {"PyCaret", "FLAML", "H2O-3", "AutoGluon"}),
    ("tune a model within a compute budget", {"FLAML", "PyCaret"}),
    ("generate features from relational data", {"Featuretools"}),
    ("evaluate which rag pipeline works best", {"AutoRAG", "Ragas", "DeepEval"}),
    ("headless browser for automation", {"Lightpanda", "Browser Use", "Browser Harness", "Stagehand"}),
    ("statistical time series forecasting", {"StatsForecast"}),
    ("translate and re-voice a video", {"pyvideotrans"}),
    # Added at 248.
    ("general purpose agent that plans and runs code", {"OpenManus", "Suna", "OpenHands"}),
    ("open source self driving stack", {"Autoware", "openpilot"}),
    ("speech recognition and synthesis in one toolkit", {"PaddleSpeech", "FunASR", "sherpa-onnx"}),
    ("let a coding agent search my whole repository", {"Claude Context", "cognee"}),
    ("train a model faster with fused kernels", {"Liger Kernel", "DeepSpeed"}),
    ("find mislabelled training data", {"Cleanlab", "Label Studio"}),
    ("adversarial attacks and defences", {"Adversarial Robustness Toolbox", "Garak", "PyRIT"}),
    # Added at 278, filling the thinnest categories: safety, evaluation,
    # fine-tuning, robotics, customer service and computer-use agents.
    ("measure bias and fairness in a model", {"AI Fairness 360", "Fairlearn"}),
    ("train with differential privacy", {"Opacus"}),
    ("holistic benchmark across many metrics", {"HELM"}),
    ("trace and score a rag pipeline", {"TruLens", "Ragas", "Phoenix", "Opik"}),
    ("reinforcement learning for language models", {"verl", "TRL", "OpenRLHF"}),
    ("simulate a self driving car", {"CARLA"}),
    ("simulate a robot arm picking things up", {"ManiSkill", "SAPIEN", "robosuite"}),
    ("visualise robot sensor data", {"Rerun"}),
    ("self hosted customer support ticketing", {"Zammad", "FreeScout", "erxes", "Chaskiq"}),
    ("let an agent control my desktop", {"Agent-S", "UI-TARS Desktop", "OpenAdapt"}),
    ("mechanistic interpretability research", {"TransformerLens"}),
    # Added at 294, filling the categories the quality report showed were both
    # thin and strong — adding to a weak neighbourhood only crowds it further.
    ("schedule a data pipeline", {"Apache Airflow", "Mage", "Prefect", "Dagster"}),
    ("durable workflow that survives a crash", {"Temporal"}),
    ("orchestrate microservices as a workflow", {"Conductor", "Temporal"}),
    ("background jobs for typescript", {"Trigger.dev"}),
    ("build an internal tool without writing a front end", {"ToolJet", "Budibase"}),
    ("run training jobs on any cloud", {"SkyPilot"}),
    ("serve a model on kubernetes", {"KServe", "Seldon Core", "Kubeflow"}),
    ("support ticketing system", {"Frappe Helpdesk", "Zammad", "FreeScout", "Chaskiq"}),
    ("chatbot across messaging platforms", {"AstrBot", "Botpress"}),
    ("answer questions from a company knowledge base", {"MaxKB", "Onyx", "AnythingLLM"}),
    # Added at 303, in the categories the quality report showed thin but
    # strong: fine-tuning (0.972), safety (0.912) and evaluation (0.908).
    ("train a model across many gpus",
     {"Colossal-AI", "GPT-NeoX", "Megatron-LM", "DeepSpeed"}),
    ("organise pytorch training code", {"PyTorch Lightning"}),
    ("faster training through algorithmic methods", {"Composer", "Liger Kernel"}),
    ("benchmark a coding agent on real github issues", {"SWE-bench"}),
    ("compare embedding models", {"MTEB"}),
    ("red team an llm application", {"DeepTeam", "Garak", "PyRIT"}),
    ("test whether an agent resists prompt injection",
     {"AgentDojo", "Rebuff", "LLM Guard"}),
    # Added at 303, pinning four use_case fields that had described a whole
    # category rather than the tool. Research and Infrastructure were the two
    # weakest neighbourhoods; sharpening these four moved them +0.058 and
    # +0.071.
    ("turn a web page into clean text for a model",
     {"Jina Reader", "Firecrawl", "Docling"}),
    ("pretrained model definitions and weights", {"Transformers"}),
    ("semantic code search over a repository for an agent",
     {"Claude Context", "cognee"}),
    ("retrieval chat with citations", {"Verba", "Onyx", "RAGFlow"}),
    # Added at 317. Research, Autonomous Agent and Robotics were the three
    # thin categories still scoring well after the use_case pass, so the
    # additions went there rather than into the crowded ones.
    ("write a cited article from web research", {"STORM", "GPT Researcher"}),
    ("self hosted answer engine with sources", {"Vane", "Morphic"}),
    ("automate a whole research cycle", {"AI Scientist", "GPT Researcher"}),
    ("retrieval behind one rest api", {"R2R", "txtai"}),
    ("give an agent a sandboxed virtual machine", {"Cua", "E2B"}),
    ("drive my own browser session", {"Nanobrowser", "Browser Use", "Automa"}),
    ("physics engine for reinforcement learning",
     {"Bullet", "MuJoCo", "Gymnasium"}),
    ("simulate a robot with ready made models",
     {"Webots", "MuJoCo Menagerie", "Gazebo"}),
    ("process point clouds", {"Open3D"}),
    ("flight control for a drone", {"PX4"}),
    ("fast motion planning on a gpu", {"cuRobo"}),
    ("support ticket queues with slas",
     {"osTicket", "Zammad", "Frappe Helpdesk", "FreeScout"}),
    ("open source crm", {"Twenty"}),
    ("team chat with customer messaging", {"Rocket.Chat", "Chatwoot"}),
    ("speech model that answers without transcribing first", {"Ultravox"}),
    # Added at 334, into the categories that were thin and already scoring
    # well: code generation, MLOps, evaluation and data analysis.
    ("sandboxed coding agent in the terminal",
     {"Codex CLI", "Claude Code", "OpenCode"}),
    ("coding agent that reads my language server", {"Crush", "Continue"}),
    ("review a pull request automatically", {"PR-Agent", "CodeRabbit"}),
    ("feature store for training and serving", {"Feast"}),
    ("high throughput gpu inference server",
     {"Triton Inference Server", "vLLM", "Ray"}),
    ("openai compatible api over local models",
     {"LocalAI", "OpenLLM", "LiteLLM", "Ollama"}),
    ("log every model call and its cost", {"Helicone", "Langfuse", "Opik"}),
    ("llm traces in opentelemetry", {"Langtrace", "OpenLLMetry"}),
    ("inspect a dataframe in a browser", {"D-Tale", "PyGWalker"}),
    ("one call report on a dataset", {"fg-data-profiling"}),
    ("data quality checks in yaml", {"Soda Core", "Great Expectations"}),
    # Added at 340, into multimodal and safety — thin, and both scoring well.
    # The TTS cluster was already eight deep and was deliberately left alone.
    ("segment an object and track it across video", {"SAM 2"}),
    ("generate a video from a text prompt", {"Open-Sora"}),
    ("speech model that can be interrupted", {"Moshi", "Ultravox"}),
    ("vision language model that runs on a phone", {"MiniCPM-V"}),
    ("audit the mcp servers an agent connects to", {"agent-scan"}),
    ("map where an agent workflow could go wrong",
     {"Agentic Radar", "AgentDojo"}),
    ("pdf to structured text keeping tables",
     {"MinerU", "Docling", "Unstructured"}),
    ("convert documents to markdown", {"Marker", "MarkItDown", "Docling"}),
    ("pull the same fields out of every document", {"Unstract"}),
    # Added at 349, every one of them surfaced by running the crawler rather
    # than from memory.
    ("penetration testing by an agent", {"Strix", "PentAGI"}),
    ("disposable sandbox for generated code", {"Daytona", "E2B"}),
    ("knowledge graph memory for an agent", {"Graphiti", "cognee", "Mem0"}),
    ("build llm applications in rust", {"Rig"}),
    ("agents that argue about a trade", {"TradingAgents"}),
    ("fail over between model providers",
     {"Bifrost", "LiteLLM", "Portkey Gateway"}),
    ("one config from data to evaluation", {"Oumi"}),
    ("fine tune from a desktop app", {"Kiln", "H2O LLM Studio"}),
    ("fine tune through a web form", {"H2O LLM Studio", "AutoTrain Advanced"}),
    ("benchmark a model across many datasets",
     {"OpenCompass", "HELM", "LM Evaluation Harness"}),
    ("benchmark a vision language model", {"VLMEvalKit"}),
    ("compare prompts side by side", {"ChainForge", "Promptfoo"}),
    ("many lora adapters on one gpu", {"LoRAX"}),
    ("route a request by meaning", {"Semantic Router"}),
    # Added at 363, into the two thinnest categories.
    ("coordinate a swarm of agents", {"ruflo", "Swarm", "CAMEL"}),
    ("identity and payments between agents", {"Bindu"}),
    ("watch several agents work on a board", {"edict", "Rowboat"}),
    ("analyse public opinion with agents", {"BettaFish"}),
    ("alert me when a topic moves", {"TrendRadar"}),
    ("question a chat export locally", {"ChatLab"}),
    ("carry context between agent sessions", {"claude-mem", "Mem0", "Letta"}),
    ("shrink tool output before the model sees it", {"Headroom"}),
    ("a personal agent i can host myself", {"nanobot", "Suna", "AgenticSeek"}),
    ("build agents as a team on one canvas", {"Sim", "Langflow", "Flowise"}),
    ("pack a repository into one prompt", {"Repomix", "Claude Context"}),
    ("ready made document chat interface",
     {"Kotaemon", "AnythingLLM", "Onyx"}),
    ("build a bot from visual blocks", {"Coze Studio", "Botpress", "Typebot"}),
    ("browse without being fingerprinted", {"CloakBrowser"}),
    ("differentiable physics for robot learning", {"Newton", "MuJoCo"}),
    ("photorealistic indoor simulation", {"Habitat-Sim", "Habitat Lab"}),
    ("random access over training data", {"Lance"}),
    ("tune an agent from production traces", {"CozeLoop", "Langfuse", "Opik"}),
])
def test_known_queries_still_surface_the_right_agents(live_store, query, expected):
    """Retrieval quality as the catalogue grows.

    Every added agent is another chance for a query to drift onto something
    less apt. Each case asserts that at least one clearly-correct agent is in
    the top 3 — loose enough not to encode one particular ranking, strict
    enough to catch a real regression.
    """
    top = [r["name"] for r in live_store.search(query, limit=3)]
    assert expected & set(top), f"{query!r} returned {top}, expected one of {sorted(expected)}"


@needs_embeddings
def test_every_category_answers_a_generic_query(live_store):
    """Regression: at 203 agents, search("agent", category="Research")
    returned nothing, though Research had 17 members.

    The over-fetch was a fixed limit*5, so it covered a shrinking share of
    the catalogue as it grew — the 25 nearest neighbours to a generic word
    happened to contain no Research entry, and the page said the category
    was empty. Growth alone will reintroduce this, which is why the check is
    over every category rather than the one that broke.
    """
    empty = []
    for category in live_store.get_categories():
        name = category["name"] if isinstance(category, dict) else category
        if not live_store.search("agent", limit=5, category=name):
            empty.append(name)

    assert not empty, f"categories that answer nothing for a generic query: {empty}"


@needs_embeddings
def test_the_maintained_filter_returns_only_live_projects(live_store):
    """19 of 223 entries are archived or dormant, and several rank highly for
    their own subject — LLM Guard and Rebuff both surface for prompt
    injection."""
    for query in ["prompt injection guardrails", "autonomous agent that runs tasks",
                  "text to speech", "agent framework"]:
        results = live_store.search(query, limit=8, maintained=True)

        assert results, f"{query!r} returned nothing with the filter on"
        stale = [r["metadata"]["name"] for r in results
                 if (r["metadata"].get("status") or "active") != "active"]
        assert not stale, f"{query!r} still returned {stale}"


@needs_embeddings
def test_the_filter_backfills_rather_than_shrinking_the_page(live_store):
    """Dropping results afterwards would hand back a short page for any query
    whose top hits happen to be abandoned."""
    for query in ["prompt injection guardrails", "voice cloning"]:
        assert len(live_store.search(query, limit=8, maintained=True)) == 8


@needs_embeddings
def test_growth_has_not_flattened_the_score_gap(live_store):
    """A bigger catalogue must still separate relevant from irrelevant."""
    good = live_store.search("agent that edits code in my terminal", limit=1)[0]
    bad = live_store.search("banana bread recipe", limit=1)[0]
    assert good["score"] - bad["score"] > 0.25


@needs_embeddings
def test_a_name_that_is_an_ordinary_word_still_finds_its_agent(live_store):
    """The case that broke the property at 150 agents.

    "Evidently" did not appear anywhere in the top ten by similarity — the
    bare adverb reads as generic English — so search now looks an exact name
    up directly rather than relying on the embedding alone.
    """
    results = live_store.search("Evidently", limit=3)
    assert results, "no results at all"
    assert results[0]["name"] == "Evidently"
    assert results[0]["match"] == "name"


@needs_embeddings
def test_a_name_match_is_not_disguised_as_similarity(live_store):
    """It scores 1.0 because it matched the name, not because it is similar."""
    top = live_store.search("Evidently", limit=1)[0]
    assert top["match"] == "name"

    # The same agent found semantically is labelled as such.
    semantic = live_store.search("detect model drift in production", limit=1)[0]
    assert semantic["match"] == "semantic"


@needs_embeddings
def test_every_agent_name_finds_its_own_agent(live_store):
    """Searching an agent's exact name must return that agent first.

    Verified across the whole catalogue rather than a sample: this is the
    property most at risk as the catalogue grows, because each new agent is
    another near neighbour competing for the top slot. Measured at 60/60 when
    this was written.
    """
    agents = live_store.get_all_agents()
    assert agents, "index is empty"

    misses = []
    for agent in agents:
        top = live_store.search(agent["name"], limit=1)
        if not top or top[0]["name"] != agent["name"]:
            misses.append((agent["name"], top[0]["name"] if top else None))

    assert not misses, f"{len(misses)} names did not rank themselves first: {misses[:5]}"


@needs_embeddings
@pytest.mark.parametrize("typo,expected", [
    ("Cursur", "Cursor"),
    ("langchian", "LangChain"),
    ("aidor", "Aider"),
    ("cluade code", "Claude Code"),
    ("open hands", "OpenHands"),
])
def test_misspelled_names_still_find_the_agent(live_store, typo, expected):
    """Users mistype. Embeddings absorb this; a keyword index would not.

    Top 3 rather than top 1: a typo legitimately sits between neighbours, and
    pinning the exact rank would make this brittle without adding value.
    """
    top = [r["name"] for r in live_store.search(typo, limit=3)]
    assert expected in top, f"{typo!r} returned {top}"


@needs_embeddings
def test_the_catalogue_and_index_agree(live_store):
    """A mismatch means somebody edited agents.json without re-seeding.

    Cheap to check and easy to get wrong: search keeps working either way, it
    just quietly returns the previous contents.
    """
    import json

    import config

    with open(config.AGENTS_JSON) as f:
        catalogue = json.load(f)

    indexed = {a["name"] for a in live_store.get_all_agents()}
    on_disk = {r["name"] for r in catalogue}

    assert indexed == on_disk, (
        f"only in the index: {sorted(indexed - on_disk)}; "
        f"only in the catalogue: {sorted(on_disk - indexed)}. Run seed.py."
    )


@needs_embeddings
def test_every_category_is_reachable_by_search(live_store):
    """Each category should surface for a query naming it.

    A category nothing can find is dead weight in the taxonomy.
    """
    categories = live_store.get_categories()
    assert categories

    unreachable = []
    for entry in categories:
        name = entry["name"]
        found = {r["metadata"].get("category") for r in live_store.search(name, limit=5)}
        if name not in found:
            unreachable.append(name)

    assert not unreachable, f"no agent surfaced for these categories: {unreachable}"


@needs_embeddings
def test_every_name_match_scores_the_same(live_store):
    """Whether the vector search returned the agent is an accident of
    retrieval. Scoring one path 1.0 and the other by similarity meant a
    min_score filter could drop an agent the user asked for by name."""
    for agent in live_store.get_all_agents()[:25]:
        top = live_store.search(agent["name"], limit=1)[0]
        assert top["name"] == agent["name"]
        assert top["match"] == "name"
        assert top["score"] == 1.0, f"{agent['name']} scored {top['score']}"


@needs_embeddings
def test_min_score_keeps_an_agent_asked_for_by_name(live_store):
    results = live_store.search("Evidently", limit=3, min_score=0.9)
    assert [r["name"] for r in results] == ["Evidently"]

