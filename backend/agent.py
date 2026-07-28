"""Agentic RAG — retrieves from the knowledge base, then answers with Claude."""

import logging
from typing import List, Dict, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

from backend.rag import retrieve

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"

# Module-level singleton — reuse across requests
_anthropic_client: anthropic.Anthropic | None = None


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def ask(
    question: str,
    screen: str = "",
    screen_data: str = "",
    history: Optional[List[Dict]] = None,
    n_results: int = 5,
) -> Dict:
    """Answer a question using RAG retrieval + Claude.

    Returns {answer: str, sources: [{source, section, snippet}]}.
    """
    # Step 1: Retrieve relevant documentation chunks
    try:
        retrieved = retrieve(question, n_results=n_results)
    except Exception as e:
        logger.warning("RAG retrieval failed, answering without knowledge base: %s", e)
        retrieved = []

    # Step 2: Build context from retrieved chunks
    context_parts = []
    sources = []
    for i, chunk in enumerate(retrieved):
        ref_num = i + 1
        context_parts.append(f"[{ref_num}] (from {chunk['source']}, section: {chunk['section']})\n{chunk['text']}")
        # Snippet: first 200 chars of the chunk for the frontend
        snippet = chunk["text"][:200].replace("\n", " ").strip()
        if len(chunk["text"]) > 200:
            snippet += "..."
        sources.append({
            "source": chunk["source"],
            "section": chunk["section"],
            "snippet": snippet,
        })

    knowledge_context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documentation found."

    # Step 3: Build the system prompt
    system_prompt = f"""You are Cloudly, an AI assistant embedded in CloudLedger — a cloud billing variance analysis tool.

You help solutions architects and finance controllers understand their cloud billing data. You are concise, specific, and always reference the actual data when answering.

You have access to two types of context:

1. KNOWLEDGE BASE — retrieved documentation about how CloudLedger works:
<knowledge_base>
{knowledge_context}
</knowledge_base>

2. SCREEN DATA — live data from the user's current screen ({screen}):
<screen_data>
{screen_data}
</screen_data>

Guidelines:
- When answering questions about how CloudLedger works (features, reason codes, variance logic), use the KNOWLEDGE BASE and cite sources using [1], [2], etc. matching the reference numbers above
- When answering questions about the user's specific billing data, use the SCREEN DATA
- When both are relevant, combine them — explain the concept from the knowledge base, then apply it to their data
- **Bold important numbers, resource names, and key findings**
- Use bullet points or numbered lists when presenting multiple findings
- Be direct and actionable — suggest next steps when relevant
- Keep responses concise (2-4 paragraphs max unless the user asks for detail)
- Do not make up data that isn't in either context source

Strict formatting rules:
- NEVER use emojis
- NEVER use hashtags
- NEVER use markdown headers (no ### or ## or #)
- Write in a professional, clean tone — like a senior consultant writing an internal memo
- Use **bold** for emphasis, bullet points for lists, and plain text for everything else"""

    # Step 4: Build messages
    messages = []
    if history:
        for h in history:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    # Step 5: Call Claude
    client = _get_anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    answer = response.content[0].text if response.content else "No response generated."

    return {
        "answer": answer,
        "sources": sources,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    question = sys.argv[1] if len(sys.argv) > 1 else "What is day normalization?"
    result = ask(question)
    print(f"\nAnswer:\n{result['answer']}")
    print(f"\nSources:")
    for i, s in enumerate(result["sources"]):
        print(f"  [{i+1}] {s['source']} — {s['section']}")
