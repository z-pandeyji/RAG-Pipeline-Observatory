from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Secure RAG Learning API"
    database_url: str = "postgresql+asyncpg://rag:rag@127.0.0.1:5432/senior_rag_quiz_lab"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "learning_chunks"
    llm_provider: str = "lmstudio"
    embedding_provider: str = "lmstudio"
    auto_create_tables: bool = False
    lmstudio_chat_url: str = "http://127.0.0.1:1234/v1/chat/completions"
    lmstudio_embedding_url: str = "http://127.0.0.1:1234/v1/embeddings"
    ollama_chat_url: str = "http://127.0.0.1:11434/api/chat"
    ollama_embedding_url: str = "http://127.0.0.1:11434/api/embeddings"
    llm_model: str = "gemma-3-4b-it"
    embedding_model: str = "nomic-embed-text"
    request_timeout_s: float = 90.0
    max_upload_mb: int = 12
    rag_top_k: int = 6
    max_context_chars: int = 12000
    quiz_top_k: int = 8
    quiz_max_context_chars: int = 10000
    quiz_default_question_count: int = 3
    quiz_temperature: float = 0.0
    quiz_auto_retry_smaller: bool = True
    quiz_max_repair_attempts: int = 1
    quiz_enable_deterministic_fallback: bool = True
    quiz_option_repair_enabled: bool = True
    quiz_dedupe_questions: bool = True
    quiz_fill_missing_with_fallback: bool = True
    debug_quiz_generation: bool = False
    ollama_json_mode: bool = True
    youtube_audio_fallback_enabled: bool = True
    youtube_max_duration_seconds: int = 1800
    transcription_provider: str = "local_whisper"
    whisper_model: str = "base"
    reranker_provider: str = "score_filter"
    rerank_min_score: float = 0.05
    rerank_dedup_threshold: float = 0.85
    query_rewriting_enabled: bool = True
    hyde_enabled: bool = False
    hybrid_search_enabled: bool = True
    embedding_dimensions: int = 1024
    chunk_target_chars: int = 1400
    chunk_overlap_chars: int = 180
    min_chunk_chars: int = 120
    youtube_merge_segments: bool = True
    youtube_target_chunk_chars: int = 1000


settings = Settings()
