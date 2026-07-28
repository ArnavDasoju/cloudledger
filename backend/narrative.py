"""AI-generated executive narrative for the close packet."""

import json
import logging

from dotenv import load_dotenv

load_dotenv()

import anthropic

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"


def generate_narrative(close_packet_data: dict) -> str:
    """Generate a 2-3 paragraph executive summary from close packet data.

    Takes the same data structure returned by the /api/close-packet endpoint.
    Returns a professional narrative suitable for CFO review.
    """
    data_str = json.dumps(close_packet_data, default=str)[:8000]

    prompt = f"""Write a 2-3 paragraph executive summary of this month's cloud billing variance.
This will appear at the top of a close packet document for the CFO.

Data:
{data_str}

Requirements:
- Start with the total spend and the month-over-month change (dollar and percentage)
- Highlight the top 2-3 drivers of cost change with specific dollar amounts
- Note how many resources are managed by IaC vs unmanaged (drift)
- If there are action items, mention them (e.g. "X resources require engineering review")
- End with the attribution coverage percentage
- Professional tone, no jargon that a finance executive wouldn't understand
- Do NOT use emojis, headers, or hashtags
- Use **bold** for key numbers
- Keep it concise — 2-3 paragraphs maximum"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text if response.content else ""
