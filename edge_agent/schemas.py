from pydantic import BaseModel


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
