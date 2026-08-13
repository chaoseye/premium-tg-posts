from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from premium_tg_posts.services.storage import LibraryStorage


class OutboxClaimTests(unittest.TestCase):
    def test_unclaimed_draft_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()

            draft = storage.save_outbox_draft("post", "<b>Hi</b>")

            self.assertIn(draft, storage.pending_drafts())

    def test_claimed_draft_is_never_pending(self) -> None:
        # Regression: the watcher polls every couple of seconds and used to pick
        # up a draft while the handler was still sending it, delivering twice.
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()

            draft = storage.save_outbox_draft("post", "<b>Hi</b>", claim=True)

            self.assertEqual(storage.pending_drafts(), [])
            self.assertTrue(storage.is_draft_sent(draft))

    def test_claim_survives_the_later_message_id_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LibraryStorage(Path(tmp))
            storage.ensure()

            draft = storage.save_outbox_draft("post", "<b>Hi</b>", claim=True)
            storage.mark_draft_sent(draft, message_id=4242)

            self.assertEqual(storage.pending_drafts(), [])
            state = storage.load_state()
            recorded = [row for row in state["sent_drafts"].values() if row["path"].endswith(draft.name)]
            self.assertEqual(len(recorded), 1, "claiming and confirming must not create two entries")
            self.assertEqual(recorded[0]["message_id"], 4242)


if __name__ == "__main__":
    unittest.main()
