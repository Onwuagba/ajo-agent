import os
from dataclasses import dataclass, field


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # python-dotenv is optional
        pass


@dataclass
class Settings:
    db_path: str = ":memory:"
    paypal_mode: str = "fake"            # fake | sandbox
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base: str = "https://api-m.sandbox.paypal.com"
    fake_webhook_secret: str = "ajo-simulated-webhook-secret"
    llm: str = "none"                    # auto (a local Ollama if running) | ollama | openai_compat | anthropic | none
    ollama_url: str = "http://127.0.0.1:11434"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    cors_origins: list[str] = field(default_factory=lambda: ["http://127.0.0.1:5180", "http://localhost:5180"])

    @classmethod
    def from_env(cls) -> "Settings":
        _load_env()
        e = os.environ.get
        llm = e("AJO_LLM", "auto")
        return cls(
            db_path=e("AJO_DB", "ajo.db"), paypal_mode=e("PAYPAL_MODE", "fake"), paypal_client_id=e("PAYPAL_CLIENT_ID", ""),
            paypal_client_secret=e("PAYPAL_CLIENT_SECRET", ""), paypal_webhook_id=e("PAYPAL_WEBHOOK_ID", ""),
            paypal_base=e("PAYPAL_BASE", "https://api-m.sandbox.paypal.com"), fake_webhook_secret=e("AJO_FAKE_WEBHOOK_SECRET", "ajo-simulated-webhook-secret"),
            llm=llm, ollama_url=e("AJO_OLLAMA_URL", "http://127.0.0.1:11434"), llm_base_url=e("AJO_LLM_BASE_URL", "https://api.tokenfactory.nebius.com/v1" if llm == "openai_compat" else ""),
            llm_api_key=e("AJO_LLM_API_KEY", ""), llm_model=e("AJO_LLM_MODEL", ""),
            cors_origins=[o for o in e("AJO_CORS", "http://127.0.0.1:5180,http://localhost:5180").split(",") if o],
        )
