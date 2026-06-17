# AI Agent Brief

You are helping create Telegram posts from locally collected materials. This project works with Codex, Claude, or any other local coding agent. Do not call OpenAI, Anthropic, or external model APIs from the Telegram bot; the bot is only the Telegram input/output surface.

## Read First

1. `storage/premium-emojis.md`
2. `storage/templates/`
3. `storage/posts/`
4. `storage/emoji-label-requests/` if the user asked to label emoji automatically
5. Any specific user instructions in the current agent chat

## How To Use The Emoji Library

Use saved premium/custom emoji through Telegram HTML tags from `storage/premium-emojis.md`:

```html
<tg-emoji emoji-id="CUSTOM_EMOJI_ID">🔥</tg-emoji>
```

Labels are optional human hints, not required metadata. If a label is missing or unclear, inspect the downloaded asset in `storage/emoji-assets` and choose based on the visual.

Asset type notes:

- `animated TGS/Lottie` means the original Telegram animation is saved as `.tgs`; a mid-frame `.svg` preview is saved in `storage/emoji-previews`. If SVG export fails, an embedded `.html` Lottie preview is saved instead.
- `video WEBM animation` means the original animation is `.webm`; a first-frame `.jpg` preview is saved in `storage/emoji-previews`.
- `static WEBP image` means the original static emoji is `.webp`; a `.png` preview is saved in `storage/emoji-previews`.

## Emoji Label Requests

If the bot saved a request in `storage/emoji-label-requests/`, read the newest request first. It contains the user's prompt plus a table of emoji IDs and asset paths.

When labeling emoji:

- Inspect the downloaded assets in `storage/emoji-assets`.
- Prefer previews in `storage/emoji-previews` for quick visual identification, then check the original asset if needed.
- Add concise labels to the matching records in `storage/emojis.json`.
- Keep `custom_emoji_id` values unchanged.
- Re-render `storage/premium-emojis.md` after editing:

```powershell
python -B -c "from pathlib import Path; from premium_tg_posts.services.storage import LibraryStorage; LibraryStorage(Path('storage')).render_emojis_markdown()"
```

## How To Use Templates And Reference Posts

- Treat templates as structure and tone guidance.
- Treat forwarded posts as examples of pacing, layout, formatting, hooks, and CTA style.
- Do not copy reference posts blindly.
- Preserve exact facts, links, prices, promo codes, winner handles, dates, and reward details provided by the user.

## Output Contract

Save the final post as an `.html` file in `storage/outbox`, for example:

```text
storage/outbox/2026-06-18-launch-post.html
```

The file must contain only the Telegram HTML message body. Do not wrap it in Markdown fences.

After saving, the bot should auto-push the draft to the detected owner. If it does not, tell the user to press `Отправить последний готовый пост` in the inline menu or use:

```text
/send_draft latest
```

## Telegram HTML Rules

- Escape literal `<`, `>`, and `&` unless they are Telegram HTML tags.
- Use valid tags such as `<b>`, `<i>`, `<u>`, `<s>`, `<tg-spoiler>`, `<a href="...">`, `<code>`, `<pre>`, `<blockquote>`, and `<tg-emoji>`.
- Keep the post concise enough for Telegram `sendMessage`.
- For custom emoji, keep a valid fallback emoji as the tag content.
