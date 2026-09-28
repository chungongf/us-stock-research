"""Provider-switchable LLM call: OpenAI or Anthropic, chosen by LLM_PROVIDER."""
from . import config

_openai = None
_anthropic = None


def provider_label() -> str:
    if config.LLM_PROVIDER == "anthropic":
        return f"anthropic / {config.ANTHROPIC_MODEL}"
    return f"openai / {config.OPENAI_MODEL}"


async def complete(prompt: str) -> str:
    if config.LLM_PROVIDER == "anthropic":
        return await _complete_anthropic(prompt)
    return await _complete_openai(prompt)


async def _complete_openai(prompt: str) -> str:
    global _openai
    if _openai is None:
        from openai import AsyncOpenAI
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _openai = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    r = await _openai.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content or ""


async def _complete_anthropic(prompt: str) -> str:
    global _anthropic
    if _anthropic is None:
        from anthropic import AsyncAnthropic
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _anthropic = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    # Streaming avoids HTTP timeouts on long inputs; server-side fallback re-runs the
    # request on another model if a safety classifier declines it.
    async with _anthropic.beta.messages.stream(
        model=config.ANTHROPIC_MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": config.ANTHROPIC_EFFORT},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = await stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("The model declined this request.")
    return "".join(b.text for b in msg.content if b.type == "text")
