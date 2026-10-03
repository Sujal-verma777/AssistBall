import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("ASSISTBALL_BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("ASSISTBALL_BACKEND_PORT", "8000")),
    )
