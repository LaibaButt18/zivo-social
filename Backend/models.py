from data_structures import LinkedList, Queue


class Content:
    def __init__(self, author, text):
        self.author = author
        self.text = text

    def display(self):
        print(self.author.name + ": " + self.text)


class Post(Content):
    def __init__(self, post_id, author, text, image=""):
        super().__init__(author, text)
        self.post_id = post_id
        self.image = image
        self.comments = LinkedList()
        self.likes = []

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
