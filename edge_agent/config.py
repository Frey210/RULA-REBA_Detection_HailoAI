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
    edge_stream_source: str = "auto"
    edge_camera_index: int = 0
    edge_camera_width: int = 640
    edge_camera_height: int = 360
    edge_camera_fps: int = 12
    edge_camera_device: str = "/dev/video0"
    edge_hailo_apps_dir: Path = Path("/home/admin/hailo-apps")
    edge_hailo_model: str = "/usr/share/hailo-models/yolov8s_pose_h8.hef"
    edge_inference_frame_fps: int = 8


settings = Settings()
