import os
import time


def main() -> None:
    session_id = os.getenv("EDGE_SESSION_ID", "SESSION_UNKNOWN")
    cam_id = os.getenv("EDGE_CAM_ID", "CAM_01")
    print(f"fake detection running for {session_id} on {cam_id}", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()

