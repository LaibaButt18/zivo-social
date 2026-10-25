import time
from urllib.parse import quote

from data_structures import Graph, Stack
from models import Blog, Chat, ChatMessage, Comment, Group, Post, User, Webinar, WebinarMessage

GROUP_AUDIENCES = ("all_members", "admins_only")
CHAT_REACTIONS = ("heart", "haha", "wow", "sad", "like")
WEBINAR_VISIBILITY = ("public", "unlisted")
WEBINAR_ROOM_CAP = 15
WEBINAR_INVITE_CAP = 50
NOTIFY_CAP = 40

#social_media.py
class SocialMedia:
    def __init__(self):
        # list keeps signup order, dict is for quick lookup by email
        self.users = []
        self.users_by_email = {}
        self.posts = []
        self.groups = []
        self.chats = []
        self.webinars = []
        self.blogs = []
        self.webinar_chat_times = {}
        self.friends = Graph()
        self.following = {}
        self.recent_profiles = Stack()
        self.next_user_id = 1
        self.next_post_id = 1
        self.next_comment_id = 1
        self.next_group_id = 1
        self.next_chat_id = 1
        self.next_message_id = 1
        self.next_webinar_id = 1
        self.next_webinar_message_id = 1
        self.next_blog_id = 1
        self.next_notification_id = 1

    def create_account(self, name, email, password, username=""):
        name = name.strip()
        email = email.strip().lower()
        password = password.strip()
        username = username.strip()

        if name == "" or email == "" or password == "":
            print("Name, email and password cannot be empty!")
            return None

        if email in self.users_by_email:
            print("Account already exists!")
            return None

        if username != "":
            for existing in self.users:
                if existing.username == username:
                    print("Username already taken!")
                    return None

        user = User(self.next_user_id, name, email, password, username)
        self.next_user_id = self.next_user_id + 1

        self.users.append(user)
        self.users_by_email[email] = user
        self.friends.add_user(email)
        print("Account created successfully!")
        return user

    def login(self, email, password):
        email = email.strip().lower()
        password = password.strip()

        if email not in self.users_by_email:
            return None

        user = self.users_by_email[email]
        if user.password != password:
            return None

        return user

    def set_password(self, email, password):
        user = self.users_by_email.get(email)
        if user is None:
            return "Account not found."

        password = password.strip()
        if len(password) < 8:
            return "Password must be at least 8 characters."

        user.password = password
        return None

    def add_friend(self, email1, email2):
        if email1 not in self.users_by_email or email2 not in self.users_by_email:
            print("User not found!")
            return

        if email1 == email2:
            print("You cannot add yourself!")
            return

        if self.friends.are_friends(email1, email2):
            print("Already friends!")
            return

        self.friends.add_friend(email1, email2)

        user1 = self.users_by_email[email1]
        user2 = self.users_by_email[email2]
        self.notify(email2, user1.name + " added you as a friend", "friend", self.profile_href(user1))
        print("Friend added!")

    def clean_poll(self, raw):
        if raw is None or raw == "" or raw == []:
            return None, None
        if not isinstance(raw, list):
            return None, "A poll needs choices."

        options = []
        seen = set()
        for item in raw:
            text = str(item or "").strip()
            if text == "":
                continue
            if len(text) > 40:
                return None, "Each poll choice can be 40 characters at most."
            key = text.casefold()
            if key in seen:
                return None, "Poll choices have to be different."
            seen.add(key)
            options.append(text)
            if len(options) > 4:
                return None, "A poll can have 4 choices at most."

        if len(options) == 0:
            return None, None
        if len(options) < 2:
            return None, "A poll needs at least 2 choices."
        return {"options": options, "votes": {}}, None

    def post_error(self, email, text, image="", group_id=0, poll=None):
        if email not in self.users_by_email:
            return "User not found."

        text = "" if text is None else str(text).strip()
        image = "" if image is None else str(image).strip()
        if image != "" and poll is not None:
            return "A post can have photos or a poll."
        if text == "" and image == "" and poll is None:
            return "Write something, add a photo, or start a poll."

        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            return "Group not found."

        if group_id != 0:
            group = self.find_group(group_id)
            if group is None:
                return "Group not found."
            if email not in group.members:
                return "Only members can post in this group."
            if not self.group_allows(group, email, "who_can_post"):
                return "Only admins can post in this group."
        return None

    def create_post(self, email, text, image="", group_id=0, images=None, poll=None):
        names = []
        for name in images or []:
            name = "" if name is None else str(name).strip()
            if name and name not in names:
                names.append(name)
            if len(names) == 4:
                break
        if not names and str(image or "").strip():
            names = [str(image).strip()]
        image = names[0] if names else ""
        message = self.post_error(email, text, image, group_id, poll)
        if message is not None:
            print(message)
            return None

        text = "" if text is None else str(text).strip()
        group_id = int(group_id)
        author = self.users_by_email[email]
        post = Post(self.next_post_id, author, text, image, group_id, names, poll)
        self.next_post_id = self.next_post_id + 1
        self.posts.append(post)
        print("Post created!")
        return post

    # linear search, the list is small for now
    def find_post(self, post_id):
        for post in self.posts:
            if post.post_id == post_id:
                return post
        return None

    def add_comment(self, email, post_id, text):
        if email not in self.users_by_email:
            print("User not found!")
            return "User not found."

        text = text.strip()
        if text == "":
            print("Comment cannot be empty!")
            return "Write a comment."

        post = self.find_post(post_id)
        if post is None:
            print("Post not found!")
            return "Post not found."

        message = self.member_can_view_post(email, post)
        if message is not None:
            return message
        if post.group_id != 0:
            group = self.find_group(post.group_id)
            if not self.group_allows(group, email, "who_can_comment"):
                return "Only admins can comment in this group."

        author = self.users_by_email[email]
        comment = Comment(self.next_comment_id, author, text)
        self.next_comment_id = self.next_comment_id + 1
        post.comments.insert_at_end(comment)
        if post.author.email != email:
            self.notify(post.author.email, author.name + " replied to your post", "comment", self.post_href(post))
        print("Comment added!")
        return None

    def like_post(self, email, post_id):
        if email not in self.users_by_email:
            return "User not found."

        post = self.find_post(post_id)
        if post is None:
            return "Post not found."

        message = self.member_can_view_post(email, post)
        if message is not None:
            return message

        if email in post.likes:
            return "You already liked this post."

        post.likes.append(email)
        if post.author.email != email:
            me = self.users_by_email[email]
            self.notify(post.author.email, me.name + " liked your post", "like", self.post_href(post))
        return None

    def update_post(self, email, post_id, text):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."
        message = self.member_can_view_post(email, post)
        if message is not None:
            return message
        if post.author.email != email:
            return "You can only edit your own posts."

        text = text.strip()
        if text == "" and not post.images and post.poll is None:
            return "Write something or keep a photo or poll."

        post.text = text
        return None

    def delete_post(self, email, post_id):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."
        message = self.member_can_view_post(email, post)
        if message is not None:
            return message
        if post.group_id != 0:
            group = self.find_group(post.group_id)
            if post.author.email != email and not self.is_group_admin(group, email):
                return "You can only delete your own posts."
        elif post.author.email != email:
            return "You can only delete your own posts."

        self.posts.remove(post)
        return None

    def vote_poll(self, email, post_id, choice):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."
        message = self.member_can_view_post(email, post)
        if message is not None:
            return message
        if post.poll is None:
            return "This post has no poll."

        try:
            choice = int(choice)
        except (TypeError, ValueError):
            return "Pick a poll choice."

        options = post.poll.get("options") or []
        if choice < 0 or choice >= len(options):
            return "Pick a poll choice."

        votes = post.poll.setdefault("votes", {})
        votes[email] = choice
        return None

    def find_comment(self, post, comment_id):
        for comment in post.comments.traverse():
            if comment.comment_id == comment_id:
                return comment
        return None

    def update_comment(self, email, post_id, comment_id, text):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."

        comment = self.find_comment(post, comment_id)
        if comment is None:
            return "Comment not found."
        message = self.member_can_view_post(email, post)
        if message is not None:
            return message
        if comment.author.email != email:
            return "You can only edit your own comments."

        text = text.strip()
        if text == "":
            return "Write a comment."

        comment.text = text
        return None

    def delete_comment(self, email, post_id, comment_id):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."

        comment = self.find_comment(post, comment_id)
        if comment is None:
            return "Comment not found."
        message = self.member_can_view_post(email, post)
        if message is not None:
            return message
        if post.group_id != 0:
            group = self.find_group(post.group_id)
            if comment.author.email != email and not self.is_group_admin(group, email):
                return "You can only delete your own comments."
        elif comment.author.email != email:
            return "You can only delete your own comments."

        post.comments.delete_where(lambda item: item.comment_id == comment_id)
        return None

    def unlike_post(self, email, post_id):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."

        message = self.member_can_view_post(email, post)
        if message is not None:
            return message

        if email not in post.likes:
            return "You have not liked this post."

        post.likes.remove(email)
        return None

    def show_users(self):
        if len(self.users) == 0:
            print("No users yet")
            return

        for user in self.users:
            print(user.name + " - " + user.email)

    def show_friends(self, email):
        if email not in self.users_by_email:
            print("User not found!")
            return

        user = self.users_by_email[email]
        friends = self.friends.get_friends(email)

        if len(friends) == 0:
            print(user.name + " has no friends yet")
            return

        print(user.name + "'s friends:")
        for friend_email in friends:
            friend = self.users_by_email[friend_email]
            print(friend.name + " - " + friend.email)

    def show_post(self, post_id):
        post = self.find_post(post_id)
        if post is None:
            print("Post not found!")
            return
        post.display()

    def view_profile(self, email):
        if email not in self.users_by_email:
            print("User not found!")
            return

        user = self.users_by_email[email]
        self.recent_profiles.push(user.email)
        print("Viewing " + user.name + " (" + user.email + ")")

    def show_notifications(self, email):
        if email not in self.users_by_email:
            print("User not found!")
            return

        user = self.users_by_email[email]
        print(user.name + "'s notifications:")
        if user.notifications.is_empty():
            print("No notifications")
            return

        for item in user.notifications.items:
            if isinstance(item, dict):
                print(item.get("text", ""))
            else:
                print(item)

    def notify(self, email, text, kind="", href=""):
        user = self.users_by_email.get(email)
        text = "" if text is None else str(text).strip()
        if user is None or text == "":
            return
        note = {
            "id": self.next_notification_id,
            "text": text[:180],
            "kind": "" if kind is None else str(kind)[:24],
            "href": "" if href is None else str(href)[:180],
            "read": False,
            "created_at": int(time.time()),
        }
        self.next_notification_id = self.next_notification_id + 1
        user.notifications.enqueue(note)
        while len(user.notifications.items) > NOTIFY_CAP:
            user.notifications.dequeue()
        if note["kind"] in ("follow", "friend", "group", "chat", "webinar", "blog"):
            try:
                from mail import send_activity_email
                send_activity_email(user.email, user.name, note["text"], note["href"])
            except Exception as err:
                print("mail: activity email failed:", err, flush=True)

    def mark_notifications(self, email, note_id=None):
        user = self.users_by_email.get(email)
        if user is None:
            return "User not found."
        if note_id is not None:
            try:
                note_id = int(note_id)
            except (TypeError, ValueError):
                return "Notification not found."
        found = note_id is None
        for item in user.notifications.items:
            if not isinstance(item, dict):
                continue
            if note_id is None or item.get("id") == note_id:
                item["read"] = True
                if note_id is not None:
                    found = True
        if not found:
            return "Notification not found."
        return None

    def unread_count(self, email):
        user = self.users_by_email.get(email)
        if user is None:
            return 0
        count = 0
        for item in user.notifications.items:
            if isinstance(item, dict) and not item.get("read"):
                count = count + 1
        return count

    def profile_href(self, user):
        key = user.username if user.username else user.email
        return "profile.html?user=" + quote(key)

    def post_href(self, post):
        if post.group_id:
            return "group.html?id=" + str(post.group_id)
        return "feed.html"

    def find_person(self, key):
        key = key.strip().lstrip("@")
        if key == "":
            return None
        if key.lower() in self.users_by_email:
            return self.users_by_email[key.lower()]
        for user in self.users:
            if user.username.lower() == key.lower():
                return user
        return None

    def follow_user(self, email, other_email):
        if email not in self.users_by_email or other_email not in self.users_by_email:
            return "User not found."
        if email == other_email:
            return "You cannot follow yourself."
        if email not in self.following:
            self.following[email] = []
        if other_email in self.following[email]:
            return "You already follow this person."
        self.following[email].append(other_email)
        me = self.users_by_email[email]
        other = self.users_by_email[other_email]
        self.notify(other_email, me.name + " started following you", "follow", self.profile_href(me))
        return None

    def unfollow_user(self, email, other_email):
        followed = self.following.get(email, [])
        if other_email not in followed:
            return "You are not following this person."
        followed.remove(other_email)
        return None

    def is_following(self, email, other_email):
        return other_email in self.following.get(email, [])

    def update_profile(self, email, name, bio, photo, cover=""):
        user = self.users_by_email[email]
        name = name.strip()
        bio = bio.strip()
        if name == "":
            return "Name cannot be empty."
        if len(bio) > 160:
            return "Bio can be 160 characters at most."
        user.name = name
        user.bio = bio
        if photo != "":
            user.photo = photo
        if cover != "":
            user.cover = cover
        return None

    def find_group(self, group_id):
        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            return None
        for group in self.groups:
            if group.group_id == group_id:
                return group
        return None

    def group_role(self, group, email):
        return group.members.get(email, "")

    def is_group_admin(self, group, email):
        return self.group_role(group, email) in ("owner", "admin")

    def group_allows(self, group, email, setting):
        if email not in group.members:
            return False
        if getattr(group, setting) == "admins_only":
            return self.is_group_admin(group, email)
        return True

    def member_can_view_post(self, email, post):
        if post.group_id == 0:
            return None
        group = self.find_group(post.group_id)
        if group is None:
            return "Group not found."
        if email not in group.members:
            return "Only members can see posts in this group."
        return None

    def posts_in_group(self, group_id):
        rows = []
        for post in self.posts:
            if post.group_id == group_id:
                rows.append(post)
        return rows

    def clean_group_text(self, name, description):
        name = name.strip()
        description = description.strip()
        if name == "":
            return "", "", "Group name cannot be empty."
        if len(name) > 60:
            return "", "", "Group name can be 60 characters at most."
        if len(description) > 300:
            return "", "", "Description can be 300 characters at most."
        return name, description, None

    def notify_group_admins(self, group, text, skip_email=""):
        for member_email, role in group.members.items():
            if role not in ("owner", "admin") or member_email == skip_email:
                continue
            self.notify(member_email, text, "group", "group.html?id=" + str(group.group_id))

    def create_group(self, email, name, description, photo=""):
        if email not in self.users_by_email:
            return None, "User not found."

        name, description, message = self.clean_group_text(name, description)
        if message is not None:
            return None, message

        group = Group(self.next_group_id, name, description, photo, email)
        self.next_group_id = self.next_group_id + 1
        group.members[email] = "owner"
        self.groups.append(group)
        return group, None

    def update_group(self, email, group_id, name, description, photo=""):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if email not in group.members:
            return "Only members can edit this group."
        if not self.group_allows(group, email, "who_can_edit"):
            return "Only admins can edit this group."

        name, description, message = self.clean_group_text(name, description)
        if message is not None:
            return message

        group.name = name
        group.description = description
        if photo != "":
            group.photo = photo
        return None

    def update_group_settings(self, email, group_id, who_can_post, who_can_comment, who_can_add, who_can_edit, require_approval):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if not self.is_group_admin(group, email):
            return "Only admins can change group permissions."
        if who_can_post not in GROUP_AUDIENCES:
            return "Post permission must be all members or admins only."
        if who_can_comment not in GROUP_AUDIENCES:
            return "Comment permission must be all members or admins only."
        if who_can_add not in GROUP_AUDIENCES:
            return "Add permission must be all members or admins only."
        if who_can_edit not in GROUP_AUDIENCES:
            return "Edit permission must be all members or admins only."
        if not isinstance(require_approval, bool):
            return "Approval setting must be on or off."

        group.who_can_post = who_can_post
        group.who_can_comment = who_can_comment
        group.who_can_add = who_can_add
        group.who_can_edit = who_can_edit
        group.require_approval = require_approval
        return None

    def join_group(self, email, group_id):
        if email not in self.users_by_email:
            return "User not found."
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if email in group.members:
            return "You are already in this group."

        user = self.users_by_email[email]
        if group.require_approval:
            if email in group.pending:
                return "You already asked to join."
            group.pending.append(email)
            self.notify_group_admins(group, user.name + " asked to join " + group.name, email)
            return None

        if email in group.pending:
            group.pending.remove(email)
        group.members[email] = "member"
        return None

    def add_group_member(self, actor_email, group_id, target_email):
        if actor_email not in self.users_by_email:
            return "User not found."
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if actor_email not in group.members:
            return "Only members can add people to this group."
        if not self.group_allows(group, actor_email, "who_can_add"):
            return "Only admins can add people to this group."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email in group.members:
            return "That person is already in the group."

        actor = self.users_by_email[actor_email]
        target = self.users_by_email[target_email]
        if self.is_group_admin(group, actor_email):
            if target_email in group.pending:
                group.pending.remove(target_email)
            group.members[target_email] = "member"
            self.notify(target_email, actor.name + " added you to " + group.name, "group", "group.html?id=" + str(group.group_id))
            return None

        if group.require_approval:
            if target_email in group.pending:
                return "That person already asked to join."
            group.pending.append(target_email)
            self.notify_group_admins(
                group,
                actor.name + " wants to add " + target.name + " to " + group.name,
                actor_email,
            )
            return None

        group.members[target_email] = "member"
        self.notify(target_email, actor.name + " added you to " + group.name, "group", "group.html?id=" + str(group.group_id))
        return None

    def remove_group_member(self, actor_email, group_id, target_email):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if not self.is_group_admin(group, actor_email):
            return "Only admins can remove people from this group."
        if target_email not in self.users_by_email:
            return "User not found."

        role = group.members.get(target_email)
        if role is None:
            return "That person is not in this group."
        if role == "owner":
            return "The owner cannot be removed."
        if actor_email == target_email:
            return "Leave the group instead of removing yourself."
        if role == "admin" and group.members.get(actor_email) != "owner":
            return "Only the owner can remove an admin."

        del group.members[target_email]
        actor = self.users_by_email.get(actor_email)
        target = self.users_by_email[target_email]
        actor_name = actor.name if actor is not None else "An admin"
        self.notify(target_email, actor_name + " removed you from " + group.name, "group", "groups.html")
        return None

    def set_group_role(self, actor_email, group_id, target_email, role):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if group.members.get(actor_email) != "owner":
            return "Only the owner can change roles."
        if role not in ("admin", "member"):
            return "Role must be admin or member."
        if target_email not in self.users_by_email:
            return "User not found."
        if actor_email == target_email:
            return "You cannot change your own role."

        current = group.members.get(target_email)
        if current is None:
            return "That person is not in this group."
        if current == "owner":
            return "The owner role cannot be changed this way."
        if current == role:
            if role == "admin":
                return "That person is already an admin."
            return "That person is already a member."

        group.members[target_email] = role
        target = self.users_by_email[target_email]
        if role == "admin":
            self.notify(target_email, "You are now an admin of " + group.name, "group", "group.html?id=" + str(group.group_id))
        else:
            self.notify(target_email, "You are no longer an admin of " + group.name, "group", "group.html?id=" + str(group.group_id))
        return None

    def approve_join(self, actor_email, group_id, target_email):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if not self.is_group_admin(group, actor_email):
            return "Only admins can approve requests."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email in group.members:
            if target_email in group.pending:
                group.pending.remove(target_email)
            return "That person is already in the group."
        if target_email not in group.pending:
            return "That person has not asked to join."

        group.pending.remove(target_email)
        group.members[target_email] = "member"
        actor = self.users_by_email.get(actor_email)
        target = self.users_by_email[target_email]
        actor_name = actor.name if actor is not None else "An admin"
        self.notify(target_email, actor_name + " approved your request to join " + group.name, "group", "group.html?id=" + str(group.group_id))
        return None

    def reject_join(self, actor_email, group_id, target_email):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if not self.is_group_admin(group, actor_email):
            return "Only admins can reject requests."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email not in group.pending:
            return "That person has not asked to join."

        group.pending.remove(target_email)
        actor = self.users_by_email.get(actor_email)
        target = self.users_by_email[target_email]
        actor_name = actor.name if actor is not None else "An admin"
        self.notify(target_email, actor_name + " declined your request to join " + group.name, "group", "groups.html")
        return None

    def group_image_names(self, group):
        names = []
        if group.photo != "":
            names.append(group.photo)
        for post in self.posts:
            if post.group_id == group.group_id:
                for name in post.images:
                    if name:
                        names.append(name)
        return names

    def drop_group(self, group):
        names = self.group_image_names(group)
        kept = []
        for post in self.posts:
            if post.group_id != group.group_id:
                kept.append(post)
        self.posts = kept
        self.groups.remove(group)
        return names

    def leave_group(self, email, group_id):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found.", []
        if email in group.pending and email not in group.members:
            group.pending.remove(email)
            return None, []
        if email not in group.members:
            return "You are not in this group.", []
        if group.members[email] == "owner":
            if len(group.members) > 1:
                return "Transfer ownership before you leave.", []
            return None, self.drop_group(group)

        del group.members[email]
        return None, []

    def transfer_group(self, actor_email, group_id, target_email):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found."
        if group.members.get(actor_email) != "owner":
            return "Only the owner can transfer this group."
        if target_email not in self.users_by_email:
            return "User not found."
        if actor_email == target_email:
            return "You already own this group."
        if target_email not in group.members:
            return "That person is not in this group."

        group.members[target_email] = "owner"
        group.members[actor_email] = "admin"
        group.owner_email = target_email
        actor = self.users_by_email[actor_email]
        target = self.users_by_email[target_email]
        self.notify(target_email, actor.name + " made you the owner of " + group.name, "group", "group.html?id=" + str(group.group_id))
        return None

    def delete_group(self, email, group_id):
        group = self.find_group(group_id)
        if group is None:
            return "Group not found.", []
        if group.members.get(email) != "owner":
            return "Only the owner can delete this group.", []
        return None, self.drop_group(group)

    def normalize_group(self, group):
        group.name = (group.name or "").strip()[:60]
        if group.name == "":
            group.name = "Group"
        group.description = (group.description or "").strip()[:300]

        cleaned = {}
        for email, role in group.members.items():
            if email not in self.users_by_email:
                continue
            if role not in ("owner", "admin", "member"):
                role = "member"
            cleaned[email] = role
        group.members = cleaned

        pending = []
        for email in group.pending:
            if email in self.users_by_email and email not in group.members and email not in pending:
                pending.append(email)
        group.pending = pending

        if group.who_can_post not in GROUP_AUDIENCES:
            group.who_can_post = "all_members"
        if group.who_can_comment not in GROUP_AUDIENCES:
            group.who_can_comment = "all_members"
        if group.who_can_add not in GROUP_AUDIENCES:
            group.who_can_add = "all_members"
        if group.who_can_edit not in GROUP_AUDIENCES:
            group.who_can_edit = "admins_only"
        if not isinstance(group.require_approval, bool):
            group.require_approval = True

        owner = group.owner_email if group.owner_email in group.members else ""
        if owner == "":
            for email, role in group.members.items():
                if role == "owner":
                    owner = email
                    break
        if owner == "" and len(group.members) > 0:
            owner = next(iter(group.members))
        if owner == "":
            return False

        for email in list(group.members):
            if email == owner:
                group.members[email] = "owner"
            elif group.members[email] == "owner":
                group.members[email] = "admin"
        group.owner_email = owner
        return True

    def find_chat(self, chat_id):
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return None
        for chat in self.chats:
            if chat.chat_id == chat_id:
                return chat
        return None

    def clean_chat_name(self, name):
        name = "" if name is None else str(name).strip()
        if name == "":
            return "", "Chat name cannot be empty."
        if len(name) > 50:
            return "", "Chat name can be 50 characters at most."
        return name, None

    def append_chat_message(self, chat, author, text, image="", system=False):
        message = ChatMessage(
            self.next_message_id,
            author,
            text,
            image,
            time.time(),
            system,
        )
        self.next_message_id = self.next_message_id + 1
        chat.messages.append(message)
        if author is not None and author.email in chat.members:
            chat.members[author.email] = message.message_id
        return message

    def create_chat(self, email, name, photo="", member_emails=None):
        if email not in self.users_by_email:
            return None, "User not found."
        name, message = self.clean_chat_name(name)
        if message is not None:
            return None, message

        chat = Chat(self.next_chat_id, name, photo, email)
        self.next_chat_id = self.next_chat_id + 1
        chat.members[email] = 0
        creator = self.users_by_email[email]
        if member_emails is None:
            member_emails = []
        for other_email in member_emails:
            if other_email == email:
                continue
            if other_email not in self.users_by_email:
                return None, "User not found."
            if other_email in chat.members:
                continue
            if len(chat.members) >= 32:
                return None, "A chat can have 32 people at most."
            chat.members[other_email] = 0

        self.chats.append(chat)
        self.append_chat_message(chat, None, creator.name + " created this chat", "", True)
        chat.members[email] = chat.messages[-1].message_id
        for other_email in list(chat.members):
            if other_email == email:
                continue
            other = self.users_by_email[other_email]
            self.notify(other_email, creator.name + " added you to " + chat.name, "chat", "chat.html?id=" + str(chat.chat_id))
        return chat, None

    def update_chat(self, email, chat_id, name, photo=""):
        chat = self.find_chat(chat_id)
        if chat is None:
            return "Chat not found."
        if email not in chat.members:
            return "Only members can edit this chat."
        name, message = self.clean_chat_name(name)
        if message is not None:
            return message
        old_name = chat.name
        chat.name = name
        if photo != "":
            chat.photo = photo
        if old_name != name:
            actor = self.users_by_email[email]
            self.append_chat_message(chat, None, actor.name + " named the chat " + name, "", True)
            chat.members[email] = chat.messages[-1].message_id
        return None

    def send_chat_message(self, email, chat_id, text, image="", reply_to=0):
        if email not in self.users_by_email:
            return None, "User not found."
        chat = self.find_chat(chat_id)
        if chat is None:
            return None, "Chat not found."
        if email not in chat.members:
            return None, "Only members can send messages in this chat."

        text = "" if text is None else str(text).strip()
        image = "" if image is None else str(image).strip()
        if text == "" and image == "":
            return None, "Write a message or add a photo."
        if len(text) > 1000:
            return None, "Messages can be 1,000 characters at most."

        try:
            reply_to = int(reply_to or 0)
        except (TypeError, ValueError):
            return None, "Reply to a message in this chat."
        if reply_to < 0 or (reply_to != 0 and self.find_chat_message(chat, reply_to) is None):
            return None, "That message is gone."

        author = self.users_by_email[email]
        message = self.append_chat_message(chat, author, text, image, False)
        message.reply_to = reply_to
        return message, None

    def find_chat_message(self, chat, message_id):
        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            return None
        for message in chat.messages:
            if message.message_id == message_id:
                return message
        return None

    def member_chat_message(self, email, chat_id, message_id):
        if email not in self.users_by_email:
            return None, None, "User not found."
        chat = self.find_chat(chat_id)
        if chat is None:
            return None, None, "Chat not found."
        if email not in chat.members:
            return None, None, "Only members can see this chat."
        message = self.find_chat_message(chat, message_id)
        if message is None:
            return None, None, "Message not found."
        return chat, message, None

    def edit_chat_message(self, email, chat_id, message_id, text):
        chat, message, error = self.member_chat_message(email, chat_id, message_id)
        if error is not None:
            return None, error
        if message.system or message.author is None:
            return None, "You can't edit that message."
        if message.author.email != email:
            return None, "You can only edit your own messages."

        text = "" if text is None else str(text).strip()
        if text == "" and message.image == "":
            return None, "Write a message or leave the photo."
        if len(text) > 1000:
            return None, "Messages can be 1,000 characters at most."
        if text != message.text:
            message.text = text
            message.edited = True
        return message, None

    def delete_chat_message(self, email, chat_id, message_id):
        chat, message, error = self.member_chat_message(email, chat_id, message_id)
        if error is not None:
            return "", error
        if message.system or message.author is None:
            return "", "You can't delete that message."
        if message.author.email != email:
            return "", "You can only delete your own messages."
        image = message.image
        chat.messages.remove(message)
        return image, None

    def react_chat_message(self, email, chat_id, message_id, emoji):
        chat, message, error = self.member_chat_message(email, chat_id, message_id)
        if error is not None:
            return error
        if message.system or message.author is None:
            return "You can't react to that message."

        emoji = "" if emoji is None else str(emoji).strip()
        current = ""
        kept = []
        for item in message.reactions:
            if item.get("email") == email:
                current = item.get("emoji", "")
                continue
            kept.append(item)
        if emoji != "" and emoji != current and emoji not in CHAT_REACTIONS:
            return "Choose a reaction from the list."
        if emoji != "" and emoji != current:
            kept.append({"email": email, "emoji": emoji})
        message.reactions = kept
        return None

    def add_chat_member(self, actor_email, chat_id, target_email):
        if actor_email not in self.users_by_email:
            return "User not found."
        chat = self.find_chat(chat_id)
        if chat is None:
            return "Chat not found."
        if actor_email not in chat.members:
            return "Only members can add people to this chat."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email in chat.members:
            return "That person is already in this chat."
        if len(chat.members) >= 32:
            return "A chat can have 32 people at most."

        latest = chat.messages[-1].message_id if chat.messages else 0
        chat.members[target_email] = latest
        actor = self.users_by_email[actor_email]
        target = self.users_by_email[target_email]
        self.append_chat_message(chat, None, actor.name + " added " + target.name, "", True)
        chat.members[actor_email] = chat.messages[-1].message_id
        self.notify(target_email, actor.name + " added you to " + chat.name, "chat", "chat.html?id=" + str(chat.chat_id))
        return None

    def remove_chat_member(self, actor_email, chat_id, target_email):
        chat = self.find_chat(chat_id)
        if chat is None:
            return "Chat not found."
        if chat.owner_email != actor_email or actor_email not in chat.members:
            return "Only the chat admin can remove people."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email not in chat.members:
            return "That person is not in this chat."
        if actor_email == target_email:
            return "Leave the chat instead of removing yourself."
        if target_email == chat.owner_email:
            return "The chat admin cannot be removed."

        actor = self.users_by_email[actor_email]
        target = self.users_by_email[target_email]
        del chat.members[target_email]
        self.append_chat_message(chat, None, actor.name + " removed " + target.name, "", True)
        chat.members[actor_email] = chat.messages[-1].message_id
        self.notify(target_email, actor.name + " removed you from " + chat.name, "chat", "chats.html")
        return None

    def chat_image_names(self, chat):
        names = []
        if chat.photo != "":
            names.append(chat.photo)
        for message in chat.messages:
            if message.image != "":
                names.append(message.image)
        return names

    def drop_chat(self, chat):
        names = self.chat_image_names(chat)
        self.chats.remove(chat)
        return names

    def leave_chat(self, email, chat_id):
        chat = self.find_chat(chat_id)
        if chat is None:
            return "Chat not found.", []
        if email not in chat.members:
            return "You are not in this chat.", []

        actor = self.users_by_email.get(email)
        actor_name = actor.name if actor is not None else "Someone"
        if len(chat.members) == 1:
            return None, self.drop_chat(chat)

        if chat.owner_email == email:
            new_owner = ""
            for member_email in chat.members:
                if member_email != email:
                    new_owner = member_email
                    break
            chat.owner_email = new_owner

        del chat.members[email]
        self.append_chat_message(chat, None, actor_name + " left the chat", "", True)
        return None, []

    def mark_chat_read(self, email, chat_id):
        chat = self.find_chat(chat_id)
        if chat is None:
            return "Chat not found."
        if email not in chat.members:
            return "Only members can see this chat."
        if chat.messages:
            chat.members[email] = chat.messages[-1].message_id
        return None

    def chat_unread(self, chat, email):
        last_read = chat.members.get(email, 0)
        count = 0
        for message in chat.messages:
            if message.message_id <= last_read:
                continue
            if message.author is not None and message.author.email == email:
                continue
            count = count + 1
        return count

    def chat_seen(self, chat, message, viewer_email):
        if message.author is None or message.author.email != viewer_email:
            return False
        if len(chat.members) < 2:
            return False
        latest = None
        for item in chat.messages:
            if item.system or item.author is None:
                continue
            if item.author.email == viewer_email:
                latest = item
        if latest is None or latest.message_id != message.message_id:
            return False
        for member_email, last_read in chat.members.items():
            if member_email == viewer_email:
                continue
            if last_read < message.message_id:
                return False
        return True

    def normalize_chat(self, chat):
        chat.name = (chat.name or "").strip()[:50]
        if chat.name == "":
            chat.name = "Chat"

        cleaned = {}
        for email, last_read in chat.members.items():
            if email not in self.users_by_email:
                continue
            try:
                last_read = int(last_read)
            except (TypeError, ValueError):
                last_read = 0
            cleaned[email] = last_read
        chat.members = cleaned
        if len(chat.members) == 0:
            return False
        if chat.owner_email not in chat.members:
            chat.owner_email = next(iter(chat.members))

        kept = []
        for message in chat.messages:
            if message.system or message.author is None:
                message.system = True
                message.author = None
                self.clean_message_meta(message)
                kept.append(message)
                continue
            if message.author.email not in self.users_by_email:
                continue
            self.clean_message_meta(message)
            kept.append(message)
            if message.message_id >= self.next_message_id:
                self.next_message_id = message.message_id + 1
        chat.messages = kept
        return True

    def clean_message_meta(self, message):
        message.edited = bool(getattr(message, "edited", False))
        try:
            message.reply_to = int(getattr(message, "reply_to", 0) or 0)
        except (TypeError, ValueError):
            message.reply_to = 0
        if message.reply_to < 0:
            message.reply_to = 0

        cleaned = []
        seen = set()
        raw = getattr(message, "reactions", None)
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                email = item.get("email", "")
                emoji = item.get("emoji", "")
                if email not in self.users_by_email or emoji not in CHAT_REACTIONS or email in seen:
                    continue
                seen.add(email)
                cleaned.append({"email": email, "emoji": emoji})
        message.reactions = cleaned
        if message.system or message.author is None:
            message.edited = False
            message.reply_to = 0
            message.reactions = []

    def find_webinar(self, webinar_id):
        try:
            webinar_id = int(webinar_id)
        except (TypeError, ValueError):
            return None
        for webinar in self.webinars:
            if webinar.webinar_id == webinar_id:
                return webinar
        return None

    def finite_time(self, value):
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return 0
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or number == float("inf") or number == float("-inf") or number < 0:
            return None
        return number

    def clean_webinar_title(self, title):
        title = "" if title is None else str(title).strip()
        if title == "":
            return "", "Webinar title cannot be empty."
        if len(title) > 80:
            return "", "Webinar title can be 80 characters at most."
        return title, None

    def clean_webinar_description(self, description):
        description = "" if description is None else str(description).strip()
        if len(description) > 300:
            return "", "Description can be 300 characters at most."
        return description, None

    def clean_webinar_visibility(self, visibility):
        visibility = "" if visibility is None else str(visibility).strip()
        if visibility == "":
            visibility = "public"
        if visibility not in WEBINAR_VISIBILITY:
            return "", "Choose public or unlisted."
        return visibility, None

    def clean_invite_emails(self, host_email, invite_emails, existing=None):
        invites = [] if existing is None else list(existing)
        if invite_emails is None:
            invite_emails = []
        for other_email in invite_emails:
            if other_email == host_email or other_email in invites:
                continue
            if other_email not in self.users_by_email:
                return None, "User not found."
            if len(invites) >= WEBINAR_INVITE_CAP:
                return None, "You can invite 50 people at most."
            invites.append(other_email)
        return invites, None

    def create_webinar(self, email, title, description="", cover="", visibility="public", starts_at=0, invite_emails=None):
        if email not in self.users_by_email:
            return None, "User not found."
        title, message = self.clean_webinar_title(title)
        if message is not None:
            return None, message
        description, message = self.clean_webinar_description(description)
        if message is not None:
            return None, message
        visibility, message = self.clean_webinar_visibility(visibility)
        if message is not None:
            return None, message
        starts_at = self.finite_time(starts_at)
        if starts_at is None:
            return None, "Choose a valid start time."
        invites, message = self.clean_invite_emails(email, invite_emails)
        if message is not None:
            return None, message

        webinar = Webinar(self.next_webinar_id, title, description, cover, email, visibility, starts_at)
        self.next_webinar_id = self.next_webinar_id + 1
        webinar.created_at = time.time()
        webinar.invited = invites
        self.webinars.append(webinar)
        host = self.users_by_email[email]
        for other_email in invites:
            self.notify(other_email, host.name + " invited you to " + webinar.title, "webinar", "webinar.html?id=" + str(webinar.webinar_id))
        return webinar, None

    def update_webinar(self, email, webinar_id, title, description, visibility, starts_at, cover=""):
        webinar = self.find_webinar(webinar_id)
        if webinar is None:
            return "Webinar not found."
        if webinar.host_email != email:
            return "Only the host can edit this webinar."
        title, message = self.clean_webinar_title(title)
        if message is not None:
            return message
        description, message = self.clean_webinar_description(description)
        if message is not None:
            return message
        visibility, message = self.clean_webinar_visibility(visibility)
        if message is not None:
            return message
        starts_at = self.finite_time(starts_at)
        if starts_at is None:
            return "Choose a valid start time."
        webinar.title = title
        webinar.description = description
        webinar.visibility = visibility
        webinar.starts_at = starts_at
        if cover != "":
            webinar.cover = cover
        return None

    def start_webinar(self, email, webinar_id):
        webinar = self.find_webinar(webinar_id)
        if webinar is None:
            return "Webinar not found."
        if webinar.host_email != email:
            return "Only the host can start this webinar."
        if webinar.status == "live":
            return "This webinar is already live."
        webinar.status = "live"
        webinar.ended_at = 0
        return None

    def end_webinar(self, email, webinar_id):
        webinar = self.find_webinar(webinar_id)
        if webinar is None:
            return "Webinar not found."
        if webinar.host_email != email:
            return "Only the host can end this webinar."
        if webinar.status != "live":
            return "This webinar is not live."
        webinar.status = "ended"
        webinar.ended_at = time.time()
        return None

    def invite_webinar(self, email, webinar_id, target_email):
        webinar = self.find_webinar(webinar_id)
        if webinar is None:
            return "Webinar not found."
        if webinar.host_email != email:
            return "Only the host can invite people."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email == webinar.host_email:
            return "You are already the host."
        if target_email in webinar.invited:
            return "That person is already invited."
        if len(webinar.invited) >= WEBINAR_INVITE_CAP:
            return "You can invite 50 people at most."
        webinar.invited.append(target_email)
        host = self.users_by_email[email]
        self.notify(target_email, host.name + " invited you to " + webinar.title, "webinar", "webinar.html?id=" + str(webinar.webinar_id))
        return None

    def pass_webinar_host(self, email, webinar_id, target_email):
        webinar = self.find_webinar(webinar_id)
        if webinar is None:
            return "Webinar not found."
        if webinar.status != "live":
            return "This webinar is not live."
        if webinar.host_email != email:
            return "Only the host can pass hosting."
        if target_email not in self.users_by_email:
            return "User not found."
        if target_email == webinar.host_email:
            return "You are already the host."
        webinar.host_email = target_email
        if target_email in webinar.invited:
            webinar.invited.remove(target_email)
        return None

    def send_webinar_message(self, email, webinar_id, text):
        if email not in self.users_by_email:
            return None, "User not found."
        webinar = self.find_webinar(webinar_id)
        if webinar is None:
            return None, "Webinar not found."
        if webinar.status != "live":
            return None, "This webinar is not live."
        text = "" if text is None else str(text).strip()
        if text == "":
            return None, "Write a message."
        if len(text) > 1000:
            return None, "Messages can be 1,000 characters at most."
        key = (webinar.webinar_id, email)
        now = time.time()
        last = self.webinar_chat_times.get(key, 0)
        if now - last < 1:
            return None, "Wait a moment before sending another message."
        self.webinar_chat_times[key] = now
        message = WebinarMessage(self.next_webinar_message_id, self.users_by_email[email], text, now)
        self.next_webinar_message_id = self.next_webinar_message_id + 1
        webinar.messages.append(message)
        return message, None

    def normalize_webinar(self, webinar):
        webinar.title = (webinar.title or "").strip()[:80]
        if webinar.title == "":
            return False
        webinar.description = (webinar.description or "").strip()[:300]
        if webinar.visibility not in WEBINAR_VISIBILITY:
            webinar.visibility = "public"
        if webinar.status not in ("scheduled", "live", "ended"):
            webinar.status = "scheduled"
        if webinar.host_email not in self.users_by_email:
            return False

        starts_at = self.finite_time(getattr(webinar, "starts_at", 0))
        webinar.starts_at = 0 if starts_at is None else starts_at
        created_at = self.finite_time(getattr(webinar, "created_at", 0))
        webinar.created_at = 0 if created_at is None else created_at
        ended_at = self.finite_time(getattr(webinar, "ended_at", 0))
        webinar.ended_at = 0 if ended_at is None else ended_at
        if webinar.status == "live":
            webinar.status = "ended"
            if webinar.ended_at <= 0:
                webinar.ended_at = time.time()

        cover = "" if webinar.cover is None else str(webinar.cover).replace("\\", "/").split("/")[-1]
        webinar.cover = cover

        invited = []
        raw_invited = webinar.invited if isinstance(webinar.invited, list) else []
        for other_email in raw_invited:
            if other_email in self.users_by_email and other_email != webinar.host_email and other_email not in invited:
                invited.append(other_email)
            if len(invited) >= WEBINAR_INVITE_CAP:
                break
        webinar.invited = invited

        kept = []
        raw_messages = webinar.messages if isinstance(webinar.messages, list) else []
        for message in raw_messages:
            if message.author is None or message.author.email not in self.users_by_email:
                continue
            message.text = (message.text or "").strip()[:1000]
            if message.text == "":
                continue
            created = self.finite_time(getattr(message, "created_at", 0))
            message.created_at = 0 if created is None else created
            kept.append(message)
            if message.message_id >= self.next_webinar_message_id:
                self.next_webinar_message_id = message.message_id + 1
        webinar.messages = kept
        return True

    def followers_of(self, email):
        found = []
        for follower, others in self.following.items():
            if email in others and follower in self.users_by_email and follower != email:
                found.append(follower)
        return found

    def find_blog(self, blog_id):
        try:
            blog_id = int(blog_id)
        except (TypeError, ValueError):
            return None
        for blog in self.blogs:
            if blog.blog_id == blog_id:
                return blog
        return None

    def clean_blog(self, title, body):
        title = "" if title is None else str(title).strip()
        body = "" if body is None else str(body).strip()
        if title == "":
            return "", "", "Add a title."
        if len(title) > 80:
            return "", "", "A title can be 80 characters at most."
        if body == "":
            return "", "", "Write the blog."
        if len(body) > 4000:
            return "", "", "A blog can be 4,000 characters at most."
        return title, body, None

    def create_blog(self, email, title, body, cover=""):
        if email not in self.users_by_email:
            return None, "User not found."
        title, body, message = self.clean_blog(title, body)
        if message is not None:
            return None, message
        author = self.users_by_email[email]
        now = int(time.time())
        blog = Blog(self.next_blog_id, author, title, body, cover, now)
        self.next_blog_id = self.next_blog_id + 1
        self.blogs.append(blog)
        label = title if len(title) <= 40 else title[:37].rstrip() + "..."
        for follower in self.followers_of(email):
            self.notify(follower, author.name + " published " + label, "blog", "blog.html?id=" + str(blog.blog_id))
        return blog, None

    def update_blog(self, email, blog_id, title, body, cover=None):
        blog = self.find_blog(blog_id)
        if blog is None:
            return "Blog not found.", ""
        if blog.author.email != email:
            return "You can only edit your own blogs.", ""
        title, body, message = self.clean_blog(title, body)
        if message is not None:
            return message, ""
        old_cover = ""
        blog.title = title
        blog.body = body
        blog.updated_at = int(time.time())
        if cover is not None:
            old_cover = blog.cover if blog.cover != cover else ""
            blog.cover = cover
        return None, old_cover

    def delete_blog(self, email, blog_id):
        blog = self.find_blog(blog_id)
        if blog is None:
            return "Blog not found.", ""
        if blog.author.email != email:
            return "You can only delete your own blogs.", ""
        cover = blog.cover
        self.blogs.remove(blog)
        return None, cover

    def like_blog(self, email, blog_id):
        if email not in self.users_by_email:
            return "User not found."
        blog = self.find_blog(blog_id)
        if blog is None:
            return "Blog not found."
        if email in blog.likes:
            return "You already liked this blog."
        blog.likes.append(email)
        if blog.author.email != email:
            me = self.users_by_email[email]
            self.notify(blog.author.email, me.name + " liked your blog", "like", "blog.html?id=" + str(blog.blog_id))
        return None

    def add_blog_comment(self, email, blog_id, text):
        if email not in self.users_by_email:
            return "User not found."
        blog = self.find_blog(blog_id)
        if blog is None:
            return "Blog not found."
        text = "" if text is None else str(text).strip()
        if text == "":
            return "Write a comment."
        if len(text) > 500:
            return "A comment can be 500 characters at most."
        author = self.users_by_email[email]
        comment = Comment(self.next_comment_id, author, text)
        self.next_comment_id = self.next_comment_id + 1
        blog.comments.insert_at_end(comment)
        if blog.author.email != email:
            self.notify(blog.author.email, author.name + " commented on your blog", "comment", "blog.html?id=" + str(blog.blog_id))
        return None

    def delete_blog_comment(self, email, blog_id, comment_id):
        blog = self.find_blog(blog_id)
        if blog is None:
            return "Blog not found."
        try:
            comment_id = int(comment_id)
        except (TypeError, ValueError):
            return "Comment not found."
        removed = blog.comments.delete_where(lambda comment: comment.comment_id == comment_id and (comment.author.email == email or blog.author.email == email))
        if not removed:
            return "Comment not found."
        return None

    def show_recent_profiles(self):
        print("Recent profiles:")
        self.recent_profiles.show()
