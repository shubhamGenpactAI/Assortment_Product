"""
guardrails.py
=============
Shared prompt-injection guardrail regex and refusal sentence.
Imported by agent_llm.py and any future LLM-touching module.
"""
import re

_INJECTION_RE = re.compile(
    r"ignore\s+(previous|above|all)\s+instructions?"
    r"|you\s+are\s+now"
    r"|forget\s+(everything|your\s+instructions?|prior|all)"
    r"|act\s+as(\s+if)?"
    r"|pretend\s+(you\s+are|to\s+be)"
    r"|new\s+(instructions?|prompt|role|persona|system)"
    r"|disregard\s+(your|all|previous)"
    r"|jailbreak|bypass\s+(guardrail|restriction|filter)"
    r"|override\s+(guardrail|instructions?|rules?)",
    re.IGNORECASE,
)

REFUSAL = (
    "I can only answer questions based on the insights "
    "and data available in this application."
)


def is_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))
