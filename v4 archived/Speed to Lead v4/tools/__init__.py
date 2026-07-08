"""WAT tools — deterministic Python the engine and AI call. The AI never acts directly: it
requests a tool, and code here executes it. Tools are the only path to side effects (Twilio,
DB, external APIs) and must be pure/testable and idempotent where they touch providers.
"""
