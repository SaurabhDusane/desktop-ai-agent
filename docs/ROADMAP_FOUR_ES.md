# Four E's Engineering Roadmap

This roadmap organizes the desktop agent around Embodiment, Efficiency, Environment, and Experience. It is an implementation plan, not a claim that these capabilities already exist.

## Product principles
1. Local-first by default: inference, working context, perception, and memory stay on-device unless the user explicitly configures an external service.
2. Policy before execution: model output is untrusted intent. Every tool call is schema-validated and authorized centrally immediately before execution.
3. Least privilege: application, resource, and operation scopes are separate. Reading does not imply writing; writing does not imply deletion.
4. Bounded autonomy: plans have step, time, concurrency, resource, and retry limits.
5. Observable behavior: the UI explains intent, execution state, approvals, failures, and recovery.
6. Learning never grants permissions or silently performs sensitive actions.
7. Graceful degradation: unavailable models and integrations must not crash the shell or bypass policy.

## The four pillars

### Embodiment
- Perception broker: UI Automation first, then accessibility metadata, OCR, and screenshot vision as needed.
- On-demand capture with explicit retention limits; no continuous screen recording by default.
- Optional local voice input/output, push-to-talk, interruption, and wake-word as separately configurable capabilities.

### Efficiency
- Model capability registry and benchmark-driven router.
- Resource-aware context manager using model token budgets, VRAM/RAM pressure, and bounded caches.
- Dependency-aware task scheduler with bounded concurrency, cancellation, deadlines, and backpressure.
- Instrumentation for latency, context usage, resource usage, cache effectiveness, and task outcomes.

### Environment
- Typed application-adapter contracts and capability declarations.
- On-demand environment state graph with event-driven refresh where available.
- Workspace snapshots and restoration, with preview and approval for changes.
- Capability-based permissions, safe paths, operation-specific scopes, and recovery/undo where technically supported.

### Experience
- Task dashboard with plan, progress, active tool, pending approval, result, and error states.
- Explainable action previews showing target, scope, expected side effects, and rollback availability.
- User-managed preferences and workflow suggestions with inspect, edit, dismiss, and delete controls.
- Accessibility, keyboard navigation, responsive UI, and clear degraded-mode status.

## Delivery sequence

### Phase 0 — Release foundation (blocker before local acceptance)
1. Complete the model-to-tool loop through the central registry; no direct model-to-shell execution.
2. Enforce schema validation, policy re-check immediately before execution, per-action approval, bounded plans, cancellation, timeouts, and structured results.
3. Add adversarial tests for prompt injection, malicious retrieved content, ambiguous targets, permission races, and emergency stop.
4. Run the complete CI matrix on Windows and Linux, then perform a documented interactive Windows + local Ollama acceptance run.

**Exit criteria:** every tool invocation is centrally authorized; denied/failed/timed-out/cancelled operations do not report success; approval races fail closed; CI is green; Windows acceptance evidence is recorded.

### Phase 1 — Environment and operational efficiency
5. Standardize application adapters and capability metadata.
6. Add environment state graph and safe workspace inspection.
7. Add task scheduler and execution observability.
8. Add model router and resource-aware context management.

**Exit criteria:** at least two application adapters work through the same contract; state is refreshed without continuous capture; concurrent read-only work is bounded; model selection and resource behavior are measured.

### Phase 2 — Embodiment
9. Add on-demand OCR/vision perception with explicit capture boundaries.
10. Add optional local voice input/output behind the same planner and policy.

**Exit criteria:** visual and voice inputs cannot bypass tool authorization; capture/audio retention settings are user-visible and tested.

### Phase 3 — Experience and learning
11. Add task dashboard and explainable action previews.
12. Integrate repetition learning with verified successful tool outcomes; store only promoted patterns, never raw transcripts or raw arguments.
13. Add user controls for learned patterns and workflow preferences.

**Exit criteria:** users can inspect task state, understand approvals, correct/delete learned preferences, and verify that learning cannot change permissions.

## Implementation workstreams

| # | Workstream | Pillar | Priority | Dependencies |
|---|---|---|---|---|
| 1 | Secure model-to-tool execution loop | Environment / Efficiency | P0 blocker | Registry, policy, approval broker |
| 2 | Capability-based permissions and recovery | Environment | P0 blocker | Workstream 1 |
| 3 | Application adapter framework | Environment | P1 | Workstreams 1–2 |
| 4 | Environment state graph | Environment / Embodiment | P1 | Workstream 3 |
| 5 | Task scheduler and observability | Efficiency / Experience | P1 | Workstream 1 |
| 6 | Intelligent model router | Efficiency | P1 | Metrics, Ollama client |
| 7 | Adaptive resource/context manager | Efficiency | P1 | Workstream 6 |
| 8 | Multimodal perception broker | Embodiment | P2 | Workstreams 1–4 |
| 9 | Local voice interaction | Embodiment / Experience | P2 | Workstream 1 |
| 10 | Task dashboard and explainability | Experience | P1 | Workstreams 1, 5 |
| 11 | Repetition learning integration and controls | Experience / Efficiency | P2 | Workstream 1, verified outcomes |

## Cross-cutting acceptance checklist
- Unit tests for success, denial, malformed inputs, exceptions, cancellation, timeout, and boundaries.
- Integration tests with fake adapters; live Windows tests are opt-in for interactive sessions.
- Security tests for untrusted model output, prompt injection, path traversal, UI ambiguity, stale approvals, and concurrent emergency stop.
- Performance tests for cold/warm model latency, memory/VRAM, context compaction, and scheduler throughput.
- No cloud calls or telemetry by default; test disabled external integrations are never contacted.
- Document permissions, data retention, recovery limits, and user-visible behavior.
- CI on supported Python versions and Windows/Linux; never mark a feature complete on an unexecuted test plan.

## Explicit initial-release non-goals
- Unrestricted shell, arbitrary Python execution, or unrestricted mouse/keyboard control.
- Continuous screen/audio recording.
- Autonomous deletion, purchases, sending messages, or other consequential actions without explicit approval.
- Persistent full conversation transcripts as a substitute for memory.
- Learned workflows changing policy, permissions, or risk classifications.


## Implementation notes

### Workstream 4 — Environment state graph (initial desktop slice)

Implemented on \`feat/local-desktop-agent\`:

- Session-local graph for current desktop workspace, process IDs, and visible windows.
- Explicit refresh through the already-authorized Windows window-list tool.
- Bounded snapshot and metadata query tools registered through the central tool registry.
- Freshness timestamp and 60-second stale indicator; refresh replaces prior observations.
- No persistence, screenshots, document contents, or background monitoring.

Still outstanding: richer process/application identity, project/workspace discovery, event-driven updates, and verified end-to-end Windows acceptance. This milestone is an initial desktop graph, not completion of all environment-state requirements.


### Workstream 5 — Task scheduler and observability (initial implementation)

Implemented on `feat/local-desktop-agent`:

- Bounded plan admission and bounded worker pool; independent read-only steps can run concurrently.
- Dependency-aware scheduling; downstream steps are skipped after failure, denial, cancellation, or deadline.
- State-changing/sensitive operations are serialized, and every step still invokes the central `ToolRegistry`.
- Cooperative cancellation and monotonic plan deadlines; in-flight third-party handlers cannot be forcibly terminated.
- Structured queued/running/completed/failed/denied/cancelled/timed-out/skipped events and rolling scheduler metrics.
- Desktop shell records task-state events in the local audit stream.

Still outstanding: model-generated plan construction and preview, live task dashboard, robust shutdown coordination for long-running handlers, per-tool cancellation, resource metrics, and executed Windows/Ollama acceptance. This is an initial scheduling service, not hard preemption or a complete task dashboard.


### Workstream 6 — Local model routing and adaptive resource management (initial implementation)

Implemented on `feat/local-desktop-agent`:

- Local Ollama metadata discovery through `/api/show` and loaded-model memory through `/api/ps`.
- Capability-aware routing for chat, tool use, vision, and code/completion; explicit model selection always wins.
- Persistent local benchmark measurements for latency and externally evaluated quality scores; no prompts or responses are stored.
- Local RAM/disk monitoring and optional NVIDIA VRAM/GPU discovery through `nvidia-smi`.
- Resource-aware session context budgeting and low-memory/VRAM warnings.
- Auto-routing option in the model selector; no model downloads or cloud routing.

Still outstanding: guided benchmark and quality-rating UI, robust VRAM estimates for unloaded models, measured cold/warm load and token-throughput benchmarks, scheduler concurrency adaptation, context-window configuration passed to Ollama, and hardware acceptance on the target RTX 4080 system. Metadata-only rankings remain provisional until benchmark measurements exist.
