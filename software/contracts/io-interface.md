# Software and Electrical I/O Interface

**Status:** Logical software behavior defined; electrical pin mapping and active levels require approval from Aratrik and Kartikay.

## Logical Channels

| Direction | Channel | Value | Purpose |
|---|---|---|---|
| Input | `part_trigger` | boolean edge | Starts one inspection after debounce |
| Output | `tower_green` | boolean | Valid PASS indication |
| Output | `tower_red` | boolean | Valid FAIL indication |
| Output | `tower_amber` | boolean | RECHECK, busy, or fault indication |
| Output | `buzzer` | boolean | Configured audible FAIL alert |
| Output | `ring_light_pwm` | integer 0-100 | Illumination duty percentage |

Logical `true` means requested/asserted behavior. The hardware adapter owns the mapping to physical voltage and active-high/active-low pins.

## State-to-Output Matrix

| State | Green | Red | Amber | Buzzer | Ring light |
|---|---:|---:|---:|---:|---:|
| STARTUP | 0 | 0 | 1 | 0 | 0 |
| READY | 0 | 0 | 0 | 0 | Configured duty |
| INSPECTING | 0 | 0 | 1 | 0 | Configured duty |
| PASS | 1 | 0 | 0 | 0 | Configured duty |
| FAIL | 0 | 1 | 0 | Configured pulse | Configured duty |
| RECHECK | 0 | 0 | 1 | 0 | Configured duty |
| FAULT | 0 | 0 | 1 if available | 0 | 0 |
| SHUTDOWN | 0 | 0 | 0 | 0 | 0 |

The critical safety rule is that PASS is deasserted during startup, inspection, uncertainty, timeout, fault, and shutdown.

## Initial Configurable Timing Defaults

| Parameter | Initial value | Rule |
|---|---:|---|
| Trigger debounce | 20 ms | Ignore unstable edges inside the window |
| Duplicate-trigger lockout | 150 ms | At most one event for one physical part |
| Inspection timeout | 250 ms | Abort to RECHECK and fault record |
| FAIL buzzer pulse | 500 ms | Non-blocking; output returns off automatically |
| Watchdog heartbeat | 100 ms | Missing two intervals enters FAULT |

These are software defaults for virtual validation, not approved electrical timing requirements.

## Adapter Behavior

Both mock and Orange Pi adapters implement:

1. `start()` and immediately request the safe startup state.
2. `read_trigger()` and return a monotonic timestamped logical edge.
3. `write_outputs(state)` atomically request the complete logical output state.
4. `health()` report ready, degraded, or unavailable with a reason.
5. `safe()` deassert PASS, FAIL, buzzer, and ring light; request amber fault indication when available.
6. `close()` enter SHUTDOWN and release resources; repeated calls are harmless.

The mock adapter records timestamped input and output transitions for automated tests. It must not require GPIO packages.

## Fault Rules

- A trigger during lockout is recorded and ignored; it does not create a second inspection event.
- An inspection timeout produces RECHECK with `INSPECTION_TIMEOUT`.
- A write failure produces RECHECK, calls `safe()`, and records `IO_WRITE_FAILURE`.
- Loss of the watchdog heartbeat calls `safe()` and records `WATCHDOG_TIMEOUT`.
- Application exit, handled signals, and unhandled exceptions call `safe()` before adapter close when possible.

## Electrical Approval Table

| Channel | Orange Pi pin | External voltage | Active level | Isolation channel | Owner approval |
|---|---|---|---|---|---|
| `part_trigger` | Open | Open | Open | Open | Aratrik + Kartikay |
| `tower_green` | Open | Open | Open | Open | Aratrik + Kartikay |
| `tower_red` | Open | Open | Open | Open | Aratrik + Kartikay |
| `tower_amber` | Open | Open | Open | Open | Aratrik + Kartikay |
| `buzzer` | Open | Open | Open | Open | Aratrik + Kartikay |
| `ring_light_pwm` | Open | Open | Open | Open | Aratrik + Kartikay |

The Orange Pi hardware adapter must not be enabled until every cell in this table is approved and copied into versioned configuration.
