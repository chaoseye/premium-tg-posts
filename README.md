# Premium Telegram Posts Collector

Local aiogram 3.x Telegram bot for collecting premium/custom emoji, reference posts, and text templates so Codex can later draft Telegram posts from the saved context.

The bot does not call OpenAI or any model API. It is only a convenient Telegram interface for:

- saving premium/custom emoji IDs and downloaded sticker files;
- labeling emoji in human language;
- saving forwarded posts with text, entities, raw JSON, and media;
- saving reusable text templates;
- sending Codex-generated HTML drafts from `storage/outbox`.

## Quick Start

1. Create a bot with `@BotFather` and copy the token.
2. Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Create `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
```

4. Put your token into `TELEGRAM_BOT_TOKEN`.
5. Start the local bot:

```powershell
python run_bot.py
```

## Bot Commands

- `/help` - show available commands.
- `/stats` - show storage counters.
- `/emojis` - list recent saved premium/custom emoji.
- `/label short_id описание` - add a human label to an emoji.
- `/label last описание` - label the most recently seen emoji.
- `/template Название\nтекст шаблона` - save a text template.
- `/template` as a reply - save the replied message as a template.
- `/post` as a reply - save the replied message as a reference post.
- `/drafts` - list Codex-generated HTML drafts.
- `/send_draft latest` - send the newest draft from `storage/outbox`.

## Normal Workflow

1. Send the bot a batch of premium/custom emoji.
2. Label the useful ones with `/label`.
3. Forward example posts to the bot.
4. Save recurring copy patterns with `/template`.
5. Open this project in Codex and ask it to read `CODEX_BRIEF.md`.
6. Codex writes the final post as an HTML file in `storage/outbox`.
7. In Telegram, run `/send_draft latest`.

## Storage Layout

- `storage/premium-emojis.md` - human-readable emoji library for Codex.
- `storage/emojis.json` - machine-readable emoji data.
- `storage/emoji-assets/` - downloaded `.webp`, `.tgs`, or `.webm` emoji files.
- `storage/templates/` - reusable text templates.
- `storage/posts/` - forwarded reference posts and media.
- `storage/raw/` - raw Telegram message JSON for templates.
- `storage/outbox/` - final HTML posts created by Codex.

## Project Layout

- `premium_tg_posts/app.py` - aiogram startup and router wiring.
- `premium_tg_posts/config.py` - `.env` settings.
- `premium_tg_posts/handlers/` - Telegram command and collection handlers.
- `premium_tg_posts/services/` - emoji, post, media, and storage logic.
- `premium_tg_posts/utils/` - small text/path helpers.

## Draft Format

Codex should save drafts as plain Telegram HTML:

```html
<tg-emoji emoji-id="5368324170671202286">🔥</tg-emoji> <b>Headline</b>

Post body...
```

The bot sends drafts with `parse_mode=HTML`. Keep each draft under Telegram's `sendMessage` text limit.

## Custom Emoji Note

Telegram requires a valid fallback emoji inside each `<tg-emoji>` tag. Depending on where the bot sends the message, custom emoji usage may also depend on the bot owner's Telegram Premium status or bot eligibility. If Telegram rejects a draft, first test in a private chat with the bot owner account.
