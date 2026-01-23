# AI Agent Discovery System

A local, privacy-focused search engine for discovering AI agents. Built with Python, Flask, LangChain, ChromaDB, and Ollama.

## Features
- **Natural Language Search**: Find agents by describing what you need (e.g., "I need an agent to write python code").
- **Semantic Ranking**: Uses RAG (Retrieval-Augmented Generation) techniques to return the most relevant results.
- **Local Privacy**: All embeddings and vector storage run locally. No data is sent to the cloud.
- **Modern UI**: Clean, dark-themed interface inspired by modern developer tools.

## Tech Stack
- **Backend**: Python, Flask
- **AI/ML**: LangChain, Ollama (Llama 3.2), ChromaDB
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Data**: Local JSON and Vector Store

## Prerequisites
- Python 3.10+
- [Ollama](https://ollama.ai) installed and running
- Model pulled: `ollama pull llama3.2` (or mistral)

## Setup

1. **Clone the repository**
   ```bash
   git clone <url>
   cd ai-agent-discovery
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   Ensure `.env` exists:
   ```env
   OLLAMA_BASE_URL=http://localhost:11434
   MODEL_NAME=llama3.2
   ```

5. **Seed Data**
   Populate the local vector database with sample agents:
   ```bash
   python seed.py
   ```

6. **Run the Application**
   ```bash
   python frontend/app.py
   ```
   Open [http://localhost:5000](http://localhost:5000) in your browser.

## API Endpoints
- `GET /api/agents` - List all agents
- `POST /api/search` - Search agents (`{"query": "..."}`)
- `GET /api/stats` - System statistics

## License
MIT
