import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

FALLBACK_MODELS = [
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b",
]


def invoke_llm_json(prompt: PromptTemplate, input_data: dict) -> dict:
    """
    Attempts to invoke ChatGroq with fallback models if rate limits (429) or model errors occur.
    Returns parsed JSON dict. Raises Exception if all models fail.
    """
    last_exception = None

    for model_name in FALLBACK_MODELS:
        try:
            llm = ChatGroq(temperature=0.0, groq_api_key=GROQ_API_KEY, model_name=model_name)
            chain = prompt | llm | JsonOutputParser()
            result = chain.invoke(input_data)
            return result
        except Exception as exc:
            exc_str = str(exc).lower()
            if "429" in exc_str or "rate limit" in exc_str or "404" in exc_str or "decommissioned" in exc_str:
                logger.warning(f"Groq model {model_name} rate-limited or error: {exc}. Trying fallback model...")
                last_exception = exc
                continue
            else:
                logger.error(f"Groq model {model_name} invocation error: {exc}")
                last_exception = exc

    raise last_exception or RuntimeError("All Groq fallback models failed")
