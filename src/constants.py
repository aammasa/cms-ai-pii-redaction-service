# Environment variable keys
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_API_KEY = "API_KEY"
ENV_API_KEY_HEADER = "API_KEY_HEADER"

# Azure Log Analytics Workspace
ENV_AZURE_LOG_WORKSPACE_ID  = "AZURE_LOG_WORKSPACE_ID"
ENV_AZURE_LOG_WORKSPACE_KEY = "AZURE_LOG_WORKSPACE_KEY"
ENV_AZURE_LOG_TYPE          = "AZURE_LOG_TYPE"

# Defaults
DEFAULT_API_KEY_HEADER = "X-API-Key"
DEFAULT_AZURE_LOG_TYPE = "PIIRedactionTrace"

# Supported file types for document extraction
SUPPORTED_FILE_TYPES: frozenset[str] = frozenset(["txt", "pdf", "docx", "doc", "csv", "md"])

# LLM used for summarization
LLM_MODEL = "claude-sonnet-4-6"

# spaCy model registry — maps ISO 639-1 code → model name
LANGUAGE_MODELS: dict[str, str] = {
    "en": "en_core_web_lg",
    "de": "de_core_news_lg",
    "fr": "fr_core_news_lg",
    "es": "es_core_news_lg",
    "nl": "nl_core_news_lg",
    "it": "it_core_news_lg",
    "sv": "sv_core_news_lg",
    "pt": "pt_core_news_lg",
    "ja": "ja_core_news_lg",
    "zh": "zh_core_web_sm",
    "ko": "xx_ent_wiki_sm",
}

LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "nl": "Dutch",
    "it": "Italian",
    "sv": "Swedish",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
}
