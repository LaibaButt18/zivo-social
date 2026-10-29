from collections import deque


class Stack:
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)

    def pop(self):
        if self.is_empty():
            return None
        return self.items.pop()

    def peek(self):
        if self.is_empty():
            return None
        return self.items[-1]

    def is_empty(self):
        return len(self.items) == 0

    def show(self):
        # last item pushed is the top
        if self.is_empty():
            print("Stack is empty")
            return

        i = len(self.items) - 1
        while i >= 0:
            print(self.items[i])
            i = i - 1


class Queue:
    def __init__(self):
        self.items = deque()

    def enqueue(self, item):
        self.items.append(item)

    def dequeue(self):
        if self.is_empty():
            return None
        return self.items.popleft()

    def is_empty(self):
        return len(self.items) == 0

    def show(self):
        if self.is_empty():
            print("Queue is empty")
            return

        for item in self.items:
            print(item)


class Node:
    def __init__(self, data):
        self.data = data
        self.next = None


class LinkedList:
    def __init__(self):
        self.head = None
        self.tail = None

    # new comments go at the end so the order stays the same
    def insert_at_end(self, data):
        new_node = Node(data)

        if self.head is None:
            self.head = new_node
            self.tail = new_node
            return

        self.tail.next = new_node
        self.tail = new_node

    def traverse(self):
        items = []
        current = self.head
        while current is not None:
            items.append(current.data)
            current = current.next
        return items

    def delete_where(self, matches):
        previous = None
        current = self.head
        while current is not None:
            if matches(current.data):
                if previous is None:
                    self.head = current.next
                else:
                    previous.next = current.next
                if current is self.tail:
                    self.tail = previous
                return True
            previous = current
            current = current.next
        return False

    def is_empty(self):
        return self.head is None


class Graph:
    def __init__(self):
        # email -> list of friend emails
        # undirected because both sides become friends
        self.adj = {}

    def add_user(self, email):
        if email not in self.adj:
            self.adj[email] = set()

    def add_friend(self, email1, email2):
        if email1 not in self.adj or email2 not in self.adj:
            return

        self.adj[email1].add(email2)
        self.adj[email2].add(email1)

    def are_friends(self, email1, email2):
        if email1 not in self.adj:
            return False
        return email2 in self.adj[email1]

    def get_friends(self, email):
        if email not in self.adj:
            return []
        return list(self.adj[email])
