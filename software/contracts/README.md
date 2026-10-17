# Software Contracts

These files define boundaries shared by more than one ForgeSight subsystem.

| Contract | Producer | Consumers |
|---|---|---|
| `inspection-event.schema.json` | Edge inspection pipeline | SQLite, FastAPI, WebSocket, HMI, evidence tooling |
| `camera-interface.md` | Camera/replay adapter | Vision and inspection orchestration |
| `io-interface.md` | Decision engine | Mock I/O, Orange Pi GPIO adapter, electrical interface |

Contract changes require a design-decision entry and review by every affected owner. Additive optional fields may retain the current major schema version; removing, renaming, or changing field meaning requires a new major version.
