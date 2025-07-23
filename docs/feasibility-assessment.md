# Feasibility assessment of the enhanced dashboard PRD

## Overall impression

- The current code base already has a solid foundation: FastAPI backend, WebSocket log streaming, structured logging, and basic web UI.
- The PRD’s Phase 1–2 goals (throttling, bounded log storage, minimal progress UI, message schemas) align well with the existing architecture, so they are broadly feasible on a 64 GB laptop.
- Phases 3–4 add enterprise-style analytics and fine-grained controls that will require substantial new surface area and might be over-scoped for a single-user tool.

## What is already covered

- WebSocket log streaming with subscribe and unsubscribe logic.
- Bounded in-memory log buffer (`LogCapture.max_entries`).
- Basic retry, concurrency limits and structured logging for PDF and OpenAI calls.
- Front-end toggle for showing logs and real-time status of the WebSocket link.

## Gaps to close before Phase 2

- No explicit throttling or batching of WebSocket messages.
- No event loop lag monitor or automatic degradation hooks.
- No end-to-end progress messages; the front-end only shows “Converting…” until the HTTP response returns.
- No pause, resume or cancel primitives in the PDF conversion pipeline.
- Missing back-end persistence (SQLite) for job state recovery.

## Laptop-specific considerations

- Memory: 64 GB gives ample headroom, so defensive limits can be generous; however, `pdf2image` and base-64 blobs still spike memory usage for large PDFs.
- CPU: Vision models and image conversion are the real bottlenecks, not the dashboard. Parallel processing will saturate CPU quickly; throttling should therefore be adaptive to CPU load, not only message count.
- Network: The app is local, so latency between back-end and front-end is negligible; batching frequency can be more relaxed (250–500 ms).

## Implementation risks

- WebSocket batching might hide real-time feedback if not tuned; users could perceive the UI as “frozen” on large PDFs.
- Pause or cancel requires cooperative cancellation inside `pdf2image` and OpenAI calls, which are blocking or remote. True interruption may not be possible without killing the task and cleaning up semaphores.
- SQLite persistence adds disk I/O for every job update; without careful throttling this can itself introduce event-loop lag.
- The front-end already contains significant JavaScript; adding charts and multi-level indicators could impact Time to Interactive unless code-split or lazy-loaded.

## Effort estimate versus personal value

- Phase 1 (safeguards) and Phase 2 (simple progress bar) are realistic and will materially improve UX for a single user.
- Phase 3 (metrics panel and interactive controls) is borderline for personal use; the additional complexity mainly serves multi-user environments.
- Phase 4 (advanced analytics) is likely overkill for a hobby project and will drive maintenance cost with limited benefit.

## Recommendations before starting

- Lock scope to Phases 1–2 for the initial release; treat Phases 3–4 as stretch goals only if real-world pain points appear.
- Implement a lightweight progress schema first. Even a simple `{"page": n, "total": m}` message sent from `OpenAIService._process_single_image` would unlock the front-end progress bar without major refactor.
- Reuse existing `LogCapture.entries` for the memory guard; add age-based eviction instead of creating a second system.
- Use a single `asyncio.create_task` for periodic event loop lag checks rather than instrumenting every await.
- Delay job persistence until you decide to support resume-on-restart; otherwise in-memory state is simpler and sufficient.
- Write integration tests that measure WebSocket message rate under realistic 200-page conversions to validate the < 10 msg/s requirement.

## Conclusion

The PRD is technically feasible, but the later phases are more sophisticated than necessary for a single-user laptop workflow. Delivering Phases 1–2 will provide immediate value with manageable risk; defer the advanced analytics and control features until you have concrete evidence that they are needed.
