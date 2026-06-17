# Repository Instructions

This project is a local Telegram collector bot for Codex-assisted premium Telegram posts.

- Do not add OpenAI API calls or model-client code to the bot.
- Keep the bot focused on collecting materials, labeling premium/custom emoji, saving reference posts, and sending files from `storage/outbox`.
- Codex-generated posts must be plain Telegram HTML files in `storage/outbox`.
- Preserve Telegram `custom_emoji_id` values exactly.
- Prefer readable Markdown context files plus structured JSON sidecars when saving user-supplied Telegram materials.
- Use `python -m unittest` and `python -m py_compile` for quick local checks.
