from pydantic import BaseModel, field_validator


class PairingInfo(BaseModel):
    service: str = "ergoquipt-edge"
    cam_id: str
    hostname: str
    status: str
    paired: bool


class PairingCompleteRequest(BaseModel):
    pairing_code: str
    backend_url: str
    edge_base_url: str | None = None


class PairingCompleteResponse(BaseModel):
    status: str
    cam_id: str
    backend_url: str


class DetectionStartRequest(BaseModel):
    session_id: str
    backend_url: str | None = None


class DetectionStatusResponse(BaseModel):
    running: bool
    pid: int | None
    command: str


class WifiConnectRequest(BaseModel):
    ssid: str
    password: str = ""

    @field_validator("ssid")
    @classmethod
    def validate_ssid(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value.encode("utf-8")) > 32 or "\x00" in value:
            raise ValueError("SSID must contain 1 to 32 bytes")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value and not 8 <= len(value) <= 63:
            raise ValueError("Wi-Fi password must contain 8 to 63 characters")
        return value
