"""Agentic RAG with tool-use — retrieves docs, calls database tools, then answers."""

import json
import logging
from typing import List, Dict, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

from backend.rag import retrieve
from backend.tools import TOOL_DEFINITIONS, _execute_tool

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_TOOL_ROUNDS = 3  # prevent infinite tool loops

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
    """Answer a question using RAG retrieval + tool-use + Claude.

    Flow:
    1. Retrieve relevant documentation from the knowledge base
    2. Send question + docs + tools to Claude
    3. If Claude calls a tool, execute it and send results back (up to MAX_TOOL_ROUNDS)
    4. Return the final text answer + sources (RAG docs + tool calls)

    Returns {answer: str, sources: [{source, section, snippet}], tools_used: [str]}.
    """
    # Step 1: RAG retrieval
    try:
        retrieved = retrieve(question, n_results=n_results)
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)
        retrieved = []

    # Build knowledge base context
    context_parts = []
    sources = []
    for i, chunk in enumerate(retrieved):
        ref_num = i + 1
        context_parts.append(f"[{ref_num}] (from {chunk['source']}, section: {chunk['section']})\n{chunk['text']}")
        snippet = chunk["text"][:200].replace("\n", " ").strip()
        if len(chunk["text"]) > 200:
            snippet += "..."
        sources.append({
            "source": chunk["source"],
            "section": chunk["section"],
            "snippet": snippet,
        })

    knowledge_context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documentation found."

    # Step 2: Build system prompt
    system_prompt = f"""You are Cloudly, an AI assistant embedded in CloudLedger — a cloud billing variance analysis tool.

You help solutions architects and finance controllers understand their cloud billing data.

You have three sources of information:

1. KNOWLEDGE BASE — retrieved documentation about how CloudLedger works:
<knowledge_base>
{knowledge_context}
</knowledge_base>

2. SCREEN DATA — live data from the user's current screen ({screen}):
<screen_data>
{screen_data}
</screen_data>

3. DATABASE TOOLS — you can query the billing database directly using the tools provided. Use tools when:
   - The user asks about specific costs, resources, or trends that aren't in the screen data
   - The user asks you to filter, search, or aggregate data
   - The user asks a question that requires looking up current numbers

Decision guide:
- Questions about how CloudLedger works → use KNOWLEDGE BASE, cite with [1], [2] etc.
- Questions about the user's specific data visible on screen → use SCREEN DATA
- Questions requiring data lookup (costs, filtering, trends, specific resources) → call a TOOL first, then answer based on the results
- When combining sources, explain the concept from docs, then apply it to the data

Formatting rules:
- **Bold important numbers and resource names**
- Use bullet points or numbered lists for multiple findings
- Be direct and actionable — suggest next steps when relevant
- Keep responses concise (2-4 paragraphs unless the user asks for detail)
- NEVER use emojis, hashtags, or markdown headers
- Professional tone — like a senior consultant writing an internal memo"""

    # Step 3: Build messages
    messages = []
    if history:
        for h in history:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    # Step 4: Tool-use loop
    client = _get_anthropic()
    tools_used = []

    for round_num in range(MAX_TOOL_ROUNDS + 1):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )

        # Check if Claude wants to use a tool
        if response.stop_reason == "tool_use":
            # Find the tool_use block(s)
            tool_results = []
            assistant_content = response.content

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    logger.info("Tool call [round %d]: %s(%s)", round_num + 1, tool_name, json.dumps(tool_input)[:100])

                    result = _execute_tool(tool_name, tool_input)
                    tools_used.append(tool_name)

                    # Add as a tool source for the frontend
                    sources.append({
                        "source": f"tool:{tool_name}",
                        "section": f"Database query: {tool_name}",
                        "snippet": result[:200] + ("..." if len(result) > 200 else ""),
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result,
                    })

            # Add assistant message + tool results to conversation
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        else:
            # Claude gave a final text response — extract it
            answer = ""
            for block in response.content:
                if hasattr(block, "text"):
                    answer += block.text

            if not answer:
                answer = "No response generated."

            return {
                "answer": answer,
                "sources": sources,
                "tools_used": tools_used,
            }

    # Fallback: hit max rounds
    return {
        "answer": "I wasn't able to complete the analysis within the allowed steps. Please try a more specific question.",
        "sources": sources,
        "tools_used": tools_used,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    question = sys.argv[1] if len(sys.argv) > 1 else "What is day normalization?"
    result = ask(question)
    print(f"\nAnswer:\n{result['answer']}")
    print(f"\nTools used: {result.get('tools_used', [])}")
    print(f"\nSources:")
    for i, s in enumerate(result["sources"]):
        print(f"  [{i+1}] {s['source']} — {s['section']}")
