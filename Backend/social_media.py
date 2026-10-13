from data_structures import Graph, Stack
from models import Comment, Post, User


class SocialMedia:
    def __init__(self):
        # list keeps signup order, dict is for quick lookup by email
        self.users = []
        self.users_by_email = {}
        self.posts = []
        self.friends = Graph()
        self.following = {}
        self.recent_profiles = Stack()
        self.next_user_id = 1
        self.next_post_id = 1
        self.next_comment_id = 1

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
        user2.notifications.enqueue(user1.name + " added you as a friend")
        print("Friend added!")

    def create_post(self, email, text, image=""):
        if email not in self.users_by_email:
            print("User not found!")
            return None

        text = text.strip()
        image = image.strip()
        if text == "" and image == "":
            print("Post cannot be empty!")
            return None

        author = self.users_by_email[email]
        post = Post(self.next_post_id, author, text, image)
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

        author = self.users_by_email[email]
        comment = Comment(self.next_comment_id, author, text)
        self.next_comment_id = self.next_comment_id + 1
        post.comments.insert_at_end(comment)
        if post.author.email != email:
            post.author.notifications.enqueue(author.name + " replied to your post")
        print("Comment added!")
        return None

    def like_post(self, email, post_id):
        if email not in self.users_by_email:
            return "User not found."

        post = self.find_post(post_id)
        if post is None:
            return "Post not found."

        if email in post.likes:
            return "You already liked this post."

        post.likes.append(email)
        if post.author.email != email:
            me = self.users_by_email[email]
            post.author.notifications.enqueue(me.name + " liked your post")
        return None

    def update_post(self, email, post_id, text):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."
        if post.author.email != email:
            return "You can only edit your own posts."

        text = text.strip()
        if text == "" and post.image == "":
            return "Write something or keep an image."

        post.text = text
        return None

    def delete_post(self, email, post_id):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."
        if post.author.email != email:
            return "You can only delete your own posts."

        self.posts.remove(post)
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
        if comment.author.email != email:
            return "You can only delete your own comments."

        post.comments.delete_where(lambda item: item.comment_id == comment_id)
        return None

    def unlike_post(self, email, post_id):
        post = self.find_post(post_id)
        if post is None:
            return "Post not found."

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

        user.notifications.show()

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
        other.notifications.enqueue(me.name + " started following you")
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

    def show_recent_profiles(self):
        print("Recent profiles:")
        self.recent_profiles.show()
