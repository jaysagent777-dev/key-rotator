"""
Provider → LiteLLM model prefix + default model mapping.
"""

PROVIDERS: dict[str, dict] = {
    "gemini": {
        "prefix": "gemini",
        "default_model": "gemini/gemini-2.0-flash",
        "env_key": "GEMINI_API_KEY",
        "label": "Google Gemini",
    },
    "groq": {
        "prefix": "groq",
        "default_model": "groq/llama-3.1-8b-instant",
        "env_key": "GROQ_API_KEY",
        "label": "Groq",
    },
    "openrouter": {
        "prefix": "openrouter",
        "default_model": "openrouter/mistralai/mistral-7b-instruct",
        "env_key": "OPENROUTER_API_KEY",
        "label": "OpenRouter",
    },
    "cohere": {
        "prefix": "cohere",
        "default_model": "command-r",
        "env_key": "COHERE_API_KEY",
        "label": "Cohere",
    },
    "mistral": {
        "prefix": "mistral",
        "default_model": "mistral/mistral-small-latest",
        "env_key": "MISTRAL_API_KEY",
        "label": "Mistral",
    },
}

# Model alias → (provider, litellm_model)
MODEL_ALIASES: dict[str, tuple[str, str]] = {
    "gpt-3.5-turbo": ("groq", "groq/llama-3.1-8b-instant"),
    "gpt-4": ("groq", "groq/llama-3.3-70b-versatile"),
    "gpt-4o": ("gemini", "gemini/gemini-2.0-flash"),
    "gpt-4o-mini": ("gemini", "gemini/gemini-2.0-flash"),
}
