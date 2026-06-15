import os
from typing import List, Dict
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODELS: List[str] = [
    "groq/compound",
    "groq/compound-mini",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-safeguard-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.1-8b-instant"
]

_current_model_index: int = -1

def get_next_model() -> str:
    global _current_model_index
    _current_model_index = (_current_model_index + 1) % len(MODELS)
    return MODELS[_current_model_index]

def call_llm(messages: List[Dict[str, str]], temperature: float = 0.2, retries: int = 0) -> str:
    """Calls the LLM and automatically rotates models on 429 errors."""
    if retries >= len(MODELS):
        raise RuntimeError("All models in the rotation are rate-limited or failing.")

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    selected_model = get_next_model()
    print(f"[LLM Router] Routing request to: {selected_model}")

    try:
        completion = client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=temperature
        )
        return completion.choices[0].message.content
    except Exception as e:
        error_msg = str(e).lower()
        # Catch 429 Rate Limits specifically, or general connection errors
        if "429" in error_msg or "rate limit" in error_msg:
            print(f"⚠️ Rate limit hit on {selected_model}. Rotating to next model...")
            return call_llm(messages, temperature, retries + 1)
        else:
            print(f"❌ Unhandled error with {selected_model}: {e}")
            return call_llm(messages, temperature, retries + 1)