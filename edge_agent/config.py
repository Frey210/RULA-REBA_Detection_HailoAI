from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    edge_cam_id: str = "CAM_01"
    edge_host: str = "0.0.0.0"
    edge_port: int = 8765
    edge_backend_url: str = "http://127.0.0.1:8000"
    edge_data_dir: Path = Path("./data")
    edge_detection_command: str = ""


settings = Settings()

