from social_media import SocialMedia

app = SocialMedia()

app.create_account("Abdullah", "test@gmail.com", "12345")
app.create_account("Laiba", "laiba@gmail.com", "67890")

# same email again
app.create_account("Abdullah", "test@gmail.com", "12345")

app.add_friend("test@gmail.com", "laiba@gmail.com")

post = app.create_post("test@gmail.com", "hello this is my first post")
app.add_comment("laiba@gmail.com", post.post_id, "nice post")

print()
app.show_users()

print()
app.show_friends("test@gmail.com")
app.show_friends("laiba@gmail.com")

print()
app.show_post(post.post_id)

print()
app.show_notifications("laiba@gmail.com")

print()
app.view_profile("laiba@gmail.com")
app.show_recent_profiles()
