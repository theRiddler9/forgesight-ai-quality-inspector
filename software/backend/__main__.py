"""Run the local API with the validated binding configuration."""

import uvicorn

from software.backend.config import BackendSettings


def main() -> None:
    settings = BackendSettings.from_environment()
    uvicorn.run("software.backend.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
