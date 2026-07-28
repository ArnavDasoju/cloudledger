"""Evaluation harness — runs eval_set.json through the RAG agent and scores results."""

import json
import logging
import os
import re
from typing import Callable, Dict, List

import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"


def _llm_judge(question: str, expected: str, actual: str, sources: List[Dict]) -> Dict:
    """Use Claude as a judge to score faithfulness, correctness, and retrieval quality."""
    source_text = "\n".join(
        f"[{i+1}] {s['source']} — {s['section']}: {s['snippet']}"
        for i, s in enumerate(sources)
    )

    prompt = f"""You are evaluating a RAG system's response. Score each dimension 1-5.

Question: {question}

Expected answer (ground truth): {expected}

Actual answer from the system: {actual}

Retrieved sources:
{source_text}

Score these three dimensions:

1. **Faithfulness** (1-5): Does the answer only contain claims supported by the retrieved sources? 5 = every claim is grounded in a source. 1 = mostly hallucinated.

2. **Correctness** (1-5): Does the answer match the expected ground truth? 5 = fully correct and complete. 1 = wrong or missing key information.

3. **Retrieval** (1-5): Did the system retrieve sources relevant to answering the question? 5 = all retrieved chunks are relevant. 1 = none are relevant.

Respond with ONLY a JSON object, no other text:
{{"faithfulness": <int>, "correctness": <int>, "retrieval": <int>, "reasoning": "<brief explanation>"}}"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Extract JSON from response — match outermost { ... } including nested content
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {"faithfulness": 0, "correctness": 0, "retrieval": 0, "reasoning": f"Failed to parse: {text[:200]}"}


def run_eval(ask_fn: Callable, eval_path: str = None) -> Dict:
    """Run evaluation against eval_set.json.

    Args:
        ask_fn: Function with signature ask(question: str) -> {answer: str, sources: [...]}
        eval_path: Path to eval_set.json. Defaults to same directory as this file.

    Returns:
        {results: [...], averages: {faithfulness, correctness, retrieval}, total: int}
    """
    if eval_path is None:
        eval_path = os.path.join(os.path.dirname(__file__), "eval_set.json")

    with open(eval_path) as f:
        eval_set = json.load(f)

    results = []
    totals = {"faithfulness": 0, "correctness": 0, "retrieval": 0}

    for i, item in enumerate(eval_set):
        question = item["question"]
        expected = item["expected_answer"]

        logger.info("Eval %d/%d: %s", i + 1, len(eval_set), question[:60])

        try:
            response = ask_fn(question)
            answer = response["answer"]
            sources = response.get("sources", [])

            scores = _llm_judge(question, expected, answer, sources)
            result = {
                "question": question,
                "expected": expected,
                "actual": answer,
                "sources": [s["source"] for s in sources],
                "scores": scores,
            }
            results.append(result)

            for k in totals:
                totals[k] += scores.get(k, 0)

        except Exception as e:
            logger.error("Eval failed for question %d: %s", i + 1, e)
            results.append({
                "question": question,
                "expected": expected,
                "actual": f"ERROR: {e}",
                "sources": [],
                "scores": {"faithfulness": 0, "correctness": 0, "retrieval": 0, "reasoning": str(e)},
            })

    n = len(eval_set)
    averages = {k: round(v / n, 2) if n > 0 else 0 for k, v in totals.items()}

    return {"results": results, "averages": averages, "total": n}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from backend.agent import ask
    report = run_eval(ask)

    print(f"\n{'='*60}")
    print(f"Evaluation Results ({report['total']} questions)")
    print(f"{'='*60}")
    print(f"  Faithfulness: {report['averages']['faithfulness']}/5")
    print(f"  Correctness:  {report['averages']['correctness']}/5")
    print(f"  Retrieval:    {report['averages']['retrieval']}/5")
    print(f"{'='*60}")

    for i, r in enumerate(report["results"]):
        s = r["scores"]
        print(f"\n[{i+1}] {r['question'][:70]}")
        print(f"    F={s.get('faithfulness',0)} C={s.get('correctness',0)} R={s.get('retrieval',0)}")
        print(f"    {s.get('reasoning','')[:120]}")
