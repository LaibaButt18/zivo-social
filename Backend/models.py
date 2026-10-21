from data_structures import LinkedList, Queue


class Content:
    def __init__(self, author, text):
        self.author = author
        self.text = text

    def display(self):
        print(self.author.name + ": " + self.text)


class Post(Content):
    def __init__(self, post_id, author, text, image="", group_id=0, images=None, poll=None):
        super().__init__(author, text)
        self.post_id = post_id
        self.group_id = group_id
        self.comments = LinkedList()
        self.likes = []
        self.images = []
        if images:
            for name in images:
                name = str(name or "").strip()
                if name and name not in self.images:
                    self.images.append(name)
                if len(self.images) == 4:
                    break
        if not self.images and str(image or "").strip():
            self.images = [str(image).strip()]
        self.image = self.images[0] if self.images else ""
        self.poll = poll if isinstance(poll, dict) else None

    def display(self):
        print("Post " + str(self.post_id))
        super().display()

        comments = self.comments.traverse()
        if len(comments) == 0:
            print("No comments")
            return

        print("Comments:")
        for comment in comments:
            comment.display()


class Comment(Content):
    def __init__(self, comment_id, author, text):
        super().__init__(author, text)
        self.comment_id = comment_id

    def display(self):
        print("Comment " + str(self.comment_id))
        super().display()


class Group:
    def __init__(self, group_id, name, description, photo, owner_email):
        self.group_id = group_id
        self.name = name
        self.description = description
        self.photo = photo
        self.owner_email = owner_email
        self.members = {}
        self.pending = []
        self.who_can_post = "all_members"
        self.who_can_comment = "all_members"
        self.who_can_add = "all_members"
        self.who_can_edit = "admins_only"
        self.require_approval = True


class ChatMessage:
    def __init__(self, message_id, author, text, image="", created_at=0, system=False, edited=False, reply_to=0, reactions=None):
        self.message_id = message_id
        self.author = author
        self.text = text
        self.image = image
        self.created_at = created_at
        self.system = system
        self.edited = edited
        self.reply_to = reply_to
        self.reactions = [] if reactions is None else reactions


class Chat:
    def __init__(self, chat_id, name, photo, owner_email):
        self.chat_id = chat_id
        self.name = name
        self.photo = photo
        self.owner_email = owner_email
        self.members = {}
        self.messages = []


class WebinarMessage:
    def __init__(self, message_id, author, text, created_at=0):
        self.message_id = message_id
        self.author = author
        self.text = text
        self.created_at = created_at


class Webinar:
    def __init__(self, webinar_id, title, description, cover, host_email, visibility="public", starts_at=0):
        self.webinar_id = webinar_id
        self.title = title
        self.description = description
        self.cover = cover
        self.host_email = host_email
        self.visibility = visibility
        self.status = "scheduled"
        self.starts_at = starts_at
        self.created_at = 0
        self.ended_at = 0
        self.invited = []
        self.messages = []


class Blog:
    def __init__(self, blog_id, author, title, body, cover="", created_at=0):
        self.blog_id = blog_id
        self.author = author
        self.title = title
        self.body = body
        self.cover = cover
        self.created_at = created_at
        self.updated_at = created_at
        self.likes = []
        self.comments = LinkedList()


class User:
    def __init__(self, user_id, name, email, password, username="", bio="", photo="", cover=""):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.password = password
        self.username = username
        self.bio = bio
        self.photo = photo
        self.cover = cover
        self.premium = False
        self.notifications = Queue()
