# Premium Telegram Posts Collector

Local aiogram 3.x Telegram bot for collecting premium/custom emoji, reference posts, and text templates so Codex, Claude, or another local AI agent can later draft Telegram posts from the saved context.

The bot does not call OpenAI or any model API. It is only a convenient Telegram interface for:

- saving premium/custom emoji IDs and downloaded sticker files;
- optionally labeling emoji in human language;
- saving forwarded posts with text, entities, raw JSON, and media;
- saving reusable text templates;
- sending AI-generated HTML drafts from `storage/outbox`;
- auto-pushing new drafts to the detected owner.

## Quick Start

1. Create a bot with `@BotFather` and copy the token.
2. Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm install
```

For `.webm` emoji previews, install `ffmpeg` and make sure it is available in `PATH`.
For `.tgs` emoji previews, the bot uses the GitHub `attikusfinch/lottie-to-svg` converter to render a Lottie frame through the SVG renderer, then saves an AI-friendly raster preview with `sharp`. The default raster format is `.png`; set `EMOJI_PREVIEW_FORMAT=webp` if you prefer `.webp`. Static `.webp` emoji previews are converted with Pillow.

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

- `/start` - open the inline button menu.
- `/help` - show the inline button menu.
- `/stats` - show storage counters.
- `/emojis` - list recent saved premium/custom emoji.
- `/label short_id описание` - optionally add a human hint to an emoji.
- `/label last описание` - optionally label the most recently seen emoji.
- `/template Название\nтекст шаблона` - save a text template.
- `/template` as a reply - save the replied message as a template.
- `/post` as a reply - save the replied message as a reference post.
- `/drafts` - list AI-generated HTML drafts.
- `/send_draft latest` - send the newest draft from `storage/outbox`.

Commands are fallback controls. The normal UI is the inline menu:

- `1. Показать базу эмодзи` - recent premium/custom emoji plus short IDs.
- `2. Добавить стиль / структуру` - the next message is saved as writing rules, format, tone, or CTA structure.
- `3. Добавить пример поста` - the next message is saved as a reference post.
- `4. Готовые посты и отправка` - outbox files and manual send button.
- `Что уже сохранено?` - storage counters.
- `Как это работает?` - short workflow explanation.
- `AI: назвать emoji по ассетам` - save a prompt for Codex / Claude to label emoji by inspecting downloaded assets.
- `Опц.: вручную назвать последний emoji` - optional human hint for the latest emoji.

## Normal Workflow

1. Send the bot a batch of premium/custom emoji.
2. Optional: label the useful ones if you want extra human meaning. Codex or Claude can also inspect downloaded assets directly.
3. Forward example posts to the bot.
4. Save recurring copy patterns with `/template`.
5. Open this project in Codex or Claude and ask it to read `AI_BRIEF.md`.
6. The AI agent writes the final post as an HTML file in `storage/outbox`.
7. The bot auto-pushes the new draft to the owner. You can also press `Отправить последний готовый пост`.

## Owner Detection

Telegram Bot API does not expose the real bot owner. This project uses local owner detection:

- if `OWNER_USER_ID` is set in `.env`, that user becomes the only owner after they message the bot in private;
- otherwise, the first private user who writes to the bot becomes owner.

The owner chat is saved in `storage/bot-state.json`. Auto-push uses that chat.

## Storage Layout

- `storage/premium-emojis.md` - human-readable emoji library for Codex, Claude, or another AI agent.
- `storage/emojis.json` - machine-readable emoji data.
- `storage/bot-state.json` - owner, user modes, and sent draft tracking.
- `storage/emoji-assets/` - downloaded `.webp`, `.tgs`, or `.webm` emoji files. These files are what the AI agent should inspect when labels are missing.
- `storage/emoji-previews/` - converted previews for quick inspection: `.tgs` -> `.svg` plus AI-friendly `.png` or `.webp`, `.webm` -> first-frame `.jpg`, `.webp` -> `.png`.
- `storage/emoji-label-requests/` - prompts for Codex / Claude to label emoji by inspecting assets.
- `storage/templates/` - reusable text templates.
- `storage/posts/` - forwarded reference posts and media.
- `storage/raw/` - raw Telegram message JSON for templates.
- `storage/outbox/` - final HTML posts created by Codex, Claude, or another AI agent.

## Project Layout

- `premium_tg_posts/app.py` - aiogram startup and router wiring.
- `premium_tg_posts/config.py` - `.env` settings.
- `premium_tg_posts/handlers/` - Telegram command and collection handlers.
- `premium_tg_posts/services/` - emoji, post, media, and storage logic.
- `premium_tg_posts/utils/` - small text/path helpers.

## Draft Format

Codex / Claude should save drafts as plain Telegram HTML:

```html
<tg-emoji emoji-id="5368324170671202286">🔥</tg-emoji> <b>Headline</b>

Post body...
```

The bot sends drafts with `parse_mode=HTML`. Keep each draft under Telegram's `sendMessage` text limit.

## Custom Emoji Note

Telegram requires a valid fallback emoji inside each `<tg-emoji>` tag. Depending on where the bot sends the message, custom emoji usage may also depend on the bot owner's Telegram Premium status or bot eligibility. If Telegram rejects a draft, first test in a private chat with the bot owner account.
