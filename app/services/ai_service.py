from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ai_settings import AISettings


async def get_settings(db: AsyncSession) -> AISettings | None:
    result = await db.execute(select(AISettings).limit(1))
    return result.scalar_one_or_none()


async def chat(
    db: AsyncSession,
    messages: List[dict],  # [{"role": "user"|"assistant", "content": str}]
    system_prompt: Optional[str] = None,
) -> str:
    settings = await get_settings(db)
    if not settings:
        return "AI sozlamalari topilmadi. Iltimos, Settings → AI sozlamalari bo'limida provider va API kalitini kiriting."

    provider = settings.provider

    try:
        if provider == "openai":
            return await _openai_chat(settings, messages, system_prompt)
        elif provider == "gemini":
            return await _gemini_chat(settings, messages, system_prompt)
        elif provider == "claude":
            return await _claude_chat(settings, messages, system_prompt)
        elif provider == "deepseek":
            return await _deepseek_chat(settings, messages, system_prompt)
        else:
            return f"Noma'lum provider: {provider}"
    except Exception as e:
        err = str(e)
        if "Connection error" in err or "connect" in err.lower():
            return "AI xatosi: Serverdan API ga ulanib bo'lmadi. API kaliti va tarmoq sozlamalarini tekshiring."
        if "401" in err or "Unauthorized" in err or "Invalid API key" in err:
            return "AI xatosi: API kalit noto'g'ri yoki muddati o'tgan. Settings → AI sozlamalarini tekshiring."
        if "429" in err or "rate" in err.lower():
            return "AI xatosi: API so'rovlar limiti oshdi. Biroz kuting."
        return f"AI xatosi: {err}"


async def _openai_chat(settings, messages, system_prompt):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=(settings.openai_api_key or "").strip())
    sys_msg = [{"role": "system", "content": system_prompt or "You are a helpful educational assistant. Respond in Uzbek."}]
    resp = await client.chat.completions.create(
        model=settings.openai_model or "gpt-4o-mini",
        messages=sys_msg + messages,
        max_tokens=1000,
    )
    return resp.choices[0].message.content


async def _gemini_chat(settings, messages, system_prompt):
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model or "gemini-1.5-flash",
        system_instruction=system_prompt or "You are a helpful educational assistant. Respond in Uzbek."
    )
    # Convert to gemini format
    history = []
    for m in messages[:-1]:
        history.append({"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]})
    chat = model.start_chat(history=history)
    resp = await chat.send_message_async(messages[-1]["content"])
    return resp.text


async def _claude_chat(settings, messages, system_prompt):
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=(settings.claude_api_key or "").strip())
    resp = await client.messages.create(
        model=settings.claude_model or "claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=system_prompt or "You are a helpful educational assistant. Respond in Uzbek.",
        messages=messages,
    )
    return resp.content[0].text


async def _deepseek_chat(settings, messages, system_prompt):
    # openai SDK v2 + DeepSeek da connection muammo bo'lgani uchun httpx to'g'ridan-to'g'ri ishlatiladi
    import httpx
    sys_msg = {"role": "system", "content": system_prompt or "You are a helpful educational assistant. Respond in Uzbek."}
    payload = {
        "model": settings.deepseek_model or "deepseek-chat",
        "messages": [sys_msg] + messages,
        "max_tokens": 1000,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {(settings.deepseek_api_key or '').strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
