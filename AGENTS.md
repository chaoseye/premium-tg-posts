# Repository Instructions

This project is a local Telegram collector bot for AI-assisted premium Telegram posts. It should work for Codex, Claude, and similar local coding agents.

- Do not add OpenAI API calls or model-client code to the bot.
- Keep the bot focused on collecting materials, labeling premium/custom emoji, saving reference posts, and sending files from `storage/outbox`.
- AI-generated posts must be plain Telegram HTML files in `storage/outbox`.
- New `storage/outbox/*.html` files should auto-push to the detected owner; keep `/send_draft` only as fallback.
- Prefer inline buttons for user-facing bot flows. Commands may exist as fallback, but should not be the primary UX.
- Preserve Telegram `custom_emoji_id` values exactly.
- Prefer readable Markdown context files plus structured JSON sidecars when saving user-supplied Telegram materials.
- Use `python -m unittest` and `python -m py_compile` for quick local checks.
