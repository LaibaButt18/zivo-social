import os
import tempfile
import unittest

os.environ.setdefault("ZIVO_DATA_DIR", tempfile.mkdtemp(prefix="zivo-perf-"))

import app
from PIL import Image
from images import resize_file


class PerfTests(unittest.TestCase):
    def test_resize_keeps_name_and_limits_edge(self):
        folder = tempfile.mkdtemp(prefix="zivo-img-")
        path = os.path.join(folder, "photo.png")
        Image.new("RGB", (2000, 1200), (20, 40, 80)).save(path, format="PNG")
        resize_file(path)
        self.assertTrue(os.path.isfile(path))
        with Image.open(path) as image:
            self.assertLessEqual(max(image.size), 1600)
            self.assertEqual(image.size[0], 1600)

    def test_post_and_group_indexes(self):
        email = "perf-posts@test.local"
        app.social.create_account("Poster", email, "password12", "perfposts")
        post = app.social.create_post(email, "hello")
        self.assertIs(app.social.find_post(post.post_id), post)
        group, err = app.social.create_group(email, "Perf", "notes")
        self.assertIsNone(err)
        grouped = app.social.create_post(email, "inside", group_id=group.group_id)
        self.assertEqual(app.social.posts_in_group(group.group_id), [grouped])
        self.assertIsNone(app.social.delete_post(email, post.post_id))
        self.assertIsNone(app.social.find_post(post.post_id))
        self.assertIs(app.social.find_post(grouped.post_id), grouped)

    def test_follow_updates_follower_count(self):
        first = "perf-a@test.local"
        second = "perf-b@test.local"
        app.social.create_account("A", first, "password12", "perfa")
        app.social.create_account("B", second, "password12", "perfb")
        self.assertIsNone(app.social.follow_user(first, second))
        self.assertEqual(app.follower_count(second), 1)
        self.assertEqual(app.social.followers_of(second), [first])
        self.assertIsNone(app.social.unfollow_user(first, second))
        self.assertEqual(app.follower_count(second), 0)

    def test_cache_clears_on_save(self):
        app.read_cache.put("posts:cache@test.local", [{"id": 1}])
        self.assertEqual(app.read_cache.get("posts:cache@test.local"), [{"id": 1}])
        app.save_data()
        self.assertIsNone(app.read_cache.get("posts:cache@test.local"))
        self.assertTrue(os.path.isfile(app.DATA_FILE))
        self.assertTrue(app.DATA_FILE.startswith(os.environ["ZIVO_DATA_DIR"]))

    def test_pool_checkout_can_be_reused(self):
        first = app.db_pool.checkout()
        app.db_pool.release(first)
        second = app.db_pool.checkout()
        try:
            row = second.execute("SELECT 1").fetchone()
            self.assertEqual(row[0], 1)
        finally:
            app.db_pool.release(second)

    def test_notification_queue_drops_oldest(self):
        email = "perf-notes@test.local"
        app.social.create_account("Notes", email, "password12", "perfnotes")
        for index in range(41):
            app.social.notify(email, "n%d" % index, "like", "")
        notes = app.social.users_by_email[email].notifications.items
        self.assertEqual(len(notes), 40)
        self.assertEqual(notes[0]["text"], "n1")
        self.assertEqual(notes[-1]["text"], "n40")


if __name__ == "__main__":
    unittest.main()
