# Codex Brief

You are helping create Telegram posts from locally collected materials. Do not call OpenAI or external model APIs from the bot; the bot is only the Telegram input/output surface.

## Read First

1. `storage/premium-emojis.md`
2. `storage/templates/`
3. `storage/posts/`
4. Any specific user instructions in the current Codex chat

## How To Use The Emoji Library

Use saved premium/custom emoji through Telegram HTML tags from `storage/premium-emojis.md`:

```html
<tg-emoji emoji-id="CUSTOM_EMOJI_ID">🔥</tg-emoji>
```

Prefer emoji with useful labels. If a label is missing but the asset exists in `storage/emoji-assets`, inspect the asset before using it.

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

After saving, tell the user to run:

```text
/send_draft latest
```

## Telegram HTML Rules

- Escape literal `<`, `>`, and `&` unless they are Telegram HTML tags.
- Use valid tags such as `<b>`, `<i>`, `<u>`, `<s>`, `<tg-spoiler>`, `<a href="...">`, `<code>`, `<pre>`, `<blockquote>`, and `<tg-emoji>`.
- Keep the post concise enough for Telegram `sendMessage`.
- For custom emoji, keep a valid fallback emoji as the tag content.
