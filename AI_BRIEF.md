# AI Agent Brief

You are helping create Telegram posts from locally collected materials. This project works with Codex, Claude, or any other local coding agent. Do not call OpenAI, Anthropic, or external model APIs from the Telegram bot; the bot is only the Telegram input/output surface.

## Read First

1. The newest `*-post-generation-request.md` or `*-emoji-label-request.md` if the bot created one.
2. The profile paths named in that request.
3. If there is no request, use the default profile paths: `storage/premium-emojis.md`, `storage/templates/`, and `storage/posts/`.
4. Any specific user instructions in the current agent chat.

## Profiles

The bot supports named profiles for different themes/projects.

- The default profile uses legacy paths such as `storage/premium-emojis.md`, `storage/posts/`, and `storage/outbox/`.
- Named profiles use `storage/profiles/<slug>/...`, for example `storage/profiles/giftstar/premium-emojis.md` and `storage/profiles/giftstar/outbox/`.
- When a post-generation request names a profile and an outbox path, follow those paths exactly.

## How To Use The Emoji Library

Use saved premium/custom emoji through Telegram HTML tags from the active profile's `premium-emojis.md`:

```html
<tg-emoji emoji-id="CUSTOM_EMOJI_ID">🔥</tg-emoji>
```

Labels are optional human hints, not required metadata. If a label is missing or unclear, inspect the downloaded asset in the same profile's `emoji-assets` directory and choose based on the visual.

### Candidate Emoji In Post Requests

A post-generation request contains a `Candidate Emoji For This Topic` table: the emoji whose labels, tags, or pack title best match the topic, each with a ready `<tg-emoji>` tag and a preview path. Prefer these candidates, but they are a shortlist and not a restriction — the full catalog stays available at the `emoji catalog` path named in the same request.

Read the note above that table. When nothing matched the topic, it says the rows are the most recently added emoji and **not** topic matches; in that case ignore the ordering and pick by inspecting the previews.

Asset type notes:

- `animated TGS/Lottie -> SVG -> PNG` or `animated TGS/Lottie -> SVG -> WEBP` means the original Telegram animation is saved as `.tgs`; the bot renders frame 3 through the SVG renderer, keeps the intermediate `.svg`, and saves an AI-friendly raster preview in `storage/emoji-previews`.
- `video WEBM animation` means the original animation is `.webm`; a first-frame `.jpg` preview is saved in `storage/emoji-previews`.
- `static WEBP image` means the original static emoji is `.webp`; a `.png` preview is saved in `storage/emoji-previews`.

## Emoji Label Requests

If the bot saved a request in `storage/emoji-label-requests/` or `storage/profiles/<slug>/emoji-label-requests/`, read the newest request first. It contains the user's prompt plus a table of emoji IDs and asset paths.

When labeling emoji:

- Inspect the downloaded assets in the request's profile `emoji-assets` directory.
- Prefer previews in the request's profile `emoji-previews` directory for quick visual identification, then check the original asset if needed.
- Add concise labels to the matching records in the profile `emojis.json`.
- Fill `tags` as well, not only `labels`. The bot matches post text against these words, so write the vocabulary a post would use to mean the emoji: synonyms, what it stands for, situations it appears in, and pronounced tone. 5-12 single words per emoji, in the language the posts are written in. A rocket is not only `ракета`; it is also `запуск`, `старт`, `релиз`, `анонс`.
- Keep `custom_emoji_id` values unchanged.
- Re-render the profile `premium-emojis.md` after editing:

```powershell
python -B -c "from pathlib import Path; from premium_tg_posts.services.storage import LibraryStorage; LibraryStorage(Path('storage')).render_emojis_markdown()"
```

## How To Use Templates And Reference Posts

- Treat templates as structure and tone guidance.
- Treat forwarded posts as examples of pacing, layout, formatting, hooks, and CTA style.
- Do not copy reference posts blindly.
- Preserve exact facts, links, prices, promo codes, winner handles, dates, and reward details provided by the user.

## Output Contract

Save the final post as an `.html` file in the outbox path named by the latest post-generation request.

If there is no request, use the default profile outbox, for example:

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
