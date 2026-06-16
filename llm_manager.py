import os
from typing import List, Dict
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODELS: List[str] = [
    "groq/compound",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
    "groq/compound-mini",
    "llama-3.1-8b-instant"
]

_current_model_index: int = -1

def get_next_model() -> str:
    """Selects the next model in the list, wrapping around to the start."""
    global _current_model_index
    _current_model_index = (_current_model_index + 1) % len(MODELS)
    return MODELS[_current_model_index]

def estimate_tokens(text: str) -> int:
    """Calculates tokens using the 1 token ≈ 0.75 English words logic."""
    words = len(text.split())
    return int(words / 0.75)

def get_messages_token_count(messages: List[Dict[str, str]]) -> int:
    """Calculates the total token count across all messages in the payload."""
    return sum(estimate_tokens(m.get("content", "")) for m in messages)

def call_llm(messages: List[Dict[str, str]], temperature: float = 0.2, retries: int = 0) -> str:
    """Calls the LLM with an embedded token safety check and repeating auto-summarization."""
    
    # Pre-flight Token Safety Check
    MAX_TOKENS = 6000  # Threshold before triggering compression
    current_tokens = get_messages_token_count(messages)
    
    compression_attempts = 0
    MAX_COMPRESSION_ATTEMPTS = 3 # Prevents an infinite loop if text can't be compressed further
    
    while current_tokens > MAX_TOKENS and compression_attempts < MAX_COMPRESSION_ATTEMPTS:
        compression_attempts += 1
        print(f"🛡️ Safety Layer: Token limit exceeded ({current_tokens} > {MAX_TOKENS}). Summarizing payload (Attempt {compression_attempts})...")
        from prompt import get_summarization_messages
        
        # Identify the largest block to compress (usually the system context or error log)
        largest_msg_idx = max(range(len(messages)), key=lambda i: len(messages[i].get("content", "")))
        summary_msgs = get_summarization_messages(messages[largest_msg_idx]["content"])
        
        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            # Use a fast, reliable model strictly for structural compression
            summary_resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=summary_msgs,
                temperature=0.1
            ).choices[0].message.content
            
            # Replace the massive text block with the compressed version
            messages[largest_msg_idx]["content"] = summary_resp
            
            # Recalculate to see if we can break out of the while loop
            current_tokens = get_messages_token_count(messages)
            print(f"✅ Compression {compression_attempts} complete. New token count: {current_tokens}")
            
        except Exception as e:
            print(f"⚠️ Summarization failed: {e}. Breaking compression loop...")
            break

    if current_tokens > MAX_TOKENS:
        print("⚠️ Warning: Payload still exceeds safe token limits after max compression attempts. Proceeding with risk of 413 error.")

    # Standard execution loop
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
        # Catch 429 Rate Limits or 413 Payload Too Large
        if "429" in error_msg or "rate limit" in error_msg or "too large" in error_msg:
            print(f"⚠️ Rate limit or 413 hit on {selected_model}. Rotating to next model...")
            return call_llm(messages, temperature, retries + 1)
        else:
            print(f"❌ Unhandled error with {selected_model}: {e}")
            return call_llm(messages, temperature, retries + 1)