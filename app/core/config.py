from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # Ollama
    ollama_host: str = Field("http://localhost:11434", env="OLLAMA_HOST")
    ollama_model: str = Field("llama3", env="OLLAMA_MODEL")

    # Workspace
    workspace_dir: Path = Field(Path("./workspaces"), env="WORKSPACE_DIR")

    # Browser agent limits
    max_routes: int = Field(20, env="MAX_ROUTES")
    max_actions_per_route: int = Field(15, env="MAX_ACTIONS_PER_ROUTE")
    dev_server_timeout: int = Field(120, env="DEV_SERVER_TIMEOUT")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
settings.workspace_dir.mkdir(parents=True, exist_ok=True)