# Contributing

Media Optimizer is currently alpha software.

## Development principles

- Preserve existing media until a replacement is verified.
- Keep observation and write operations clearly separated.
- New write functionality must include safety tests.
- Never log or commit API keys or credentials.
- Prefer stable provider IDs over title matching.
- Historical playback uncertainty must fail safe.

## Validation

Run ./scripts/validate.sh before submitting changes.

All tests and safety checks must pass.
