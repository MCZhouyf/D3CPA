# LLM ledger semantics

The ledger records a logical Planner/Reflection call and every relay attempt.
It stores hashes rather than prompt bodies and never stores credentials.  Token
counts are marked `api_usage` only when the relay returns valid usage metadata;
otherwise all count fields are null and `token_count_source=unavailable`.
Rate-limit retries are individual relay attempts attached to one logical call.
