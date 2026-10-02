# Software

Owned by Riya and Akash.

## Planned Areas

| Folder | Contents |
|---|---|
| `contracts/` | Shared event, camera, configuration, and I/O contracts |
| `dataset/` | Dataset card, labeling guide, manifests, and split metadata |
| `vision/` | Capture, preprocessing, replay, and deterministic Poka-Yoke |
| `ml/` | Training, evaluation, ONNX export, and RKNN compilation |
| `edge/` | Decision engine, I/O adapters, watchdog, and service orchestration |
| `backend/` | FastAPI, WebSocket, SQLite migrations, and audit services |
| `frontend/` | React touchscreen HMI |
| `deployment/` | Orange Pi environment and service configuration |
| `tests/` | Cross-module fixtures and acceptance tests |

Hardware access must remain behind adapters so recorded fixtures and mock I/O can exercise the full pipeline on a development machine.
