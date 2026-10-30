var POST_ICONS = {
  reply: '<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>',
  repost: '<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>',
  like: '<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
  share: '<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v13"/></svg>',
};

function openDialog(options) {
  return new Promise(function (resolve) {
    var overlay = document.createElement('div');
    overlay.className = 'zivo-modal';
    var card = document.createElement('div');
    card.className = 'zivo-modal-card';
    card.setAttribute('role', 'alertdialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-labelledby', 'zivo-dialog-title');

    var title = document.createElement('h2');
    title.id = 'zivo-dialog-title';
    title.className = 'zivo-modal-title';
    title.textContent = options.title;

    var body = document.createElement('p');
    body.className = 'zivo-modal-body';
    body.textContent = options.body || '';
    if (!options.body) body.hidden = true;

    var actions = document.createElement('div');
    actions.className = 'zivo-modal-actions';

    function finish(value) {
      document.removeEventListener('keydown', onKey);
      overlay.remove();
      resolve(value);
    }

    function onKey(event) {
      if (event.key === 'Escape') finish(false);
    }

    if (options.confirmLabel) {
      var yes = document.createElement('button');
      yes.type = 'button';
      yes.className = 'zivo-modal-danger';
      yes.textContent = options.confirmLabel;
      var no = document.createElement('button');
      no.type = 'button';
      no.className = 'zivo-modal-cancel';
      no.textContent = 'Cancel';
      yes.addEventListener('click', function () { finish(true); });
      no.addEventListener('click', function () { finish(false); });
      actions.appendChild(yes);
      actions.appendChild(no);
    } else {
      var ok = document.createElement('button');
      ok.type = 'button';
      ok.className = 'zivo-modal-ok';
      ok.textContent = 'OK';
      ok.addEventListener('click', function () { finish(true); });
      actions.appendChild(ok);
    }

    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) finish(!!options.confirmLabel === false);
    });

    card.appendChild(title);
    card.appendChild(body);
    card.appendChild(actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    document.addEventListener('keydown', onKey);
    actions.lastElementChild.focus();
  });
}

function applyPostUpdate(post, updated) {
  post.liked = !!updated.liked;
  post.like_count = updated.like_count || 0;
  post.comments = updated.comments || [];
  if (typeof updated.text === 'string') post.text = updated.text;
}

function mountPostMenu(header, post, helpers) {
  var isAuthor = !!(helpers && helpers.meEmail === post.email);
  var canModerate = !!(helpers && helpers.canModerate);
  if (!isAuthor && !canModerate) return;

  var textEl = helpers.textEl;
  var wrap = document.createElement('div');
  wrap.className = 'relative -mr-1 shrink-0';

  var button = document.createElement('button');
  button.type = 'button';
  button.className = 'rounded-full p-1.5 text-x-muted hover:bg-x-blue/10 hover:text-x-blue';
  button.setAttribute('aria-label', 'More');
  button.setAttribute('aria-haspopup', 'menu');
  button.innerHTML = '<svg viewBox="0 0 24 24" class="size-5" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>';

  var menu = document.createElement('div');
  menu.className = 'menu-pop absolute right-0 z-20 hidden w-36 overflow-hidden rounded-xl bg-x-panel py-1';
  menu.setAttribute('role', 'menu');
  menu.setAttribute('data-own-menu', '');

  function menuItem(label, danger) {
    var el = document.createElement('button');
    el.type = 'button';
    el.setAttribute('role', 'menuitem');
    el.className = 'block w-full px-4 py-2.5 text-left text-[15px] font-bold hover:bg-x-hover';
    if (danger) el.classList.add('text-x-danger');
    el.textContent = label;
    return el;
  }

  var editItem = menuItem('Edit');
  var deleteItem = menuItem('Delete', true);
  if (isAuthor) menu.appendChild(editItem);
  menu.appendChild(deleteItem);

  var editor = document.createElement('form');
  editor.className = 'mt-2 hidden';
  var area = document.createElement('textarea');
  area.rows = 3;
  area.className = 'w-full resize-none rounded-2xl border border-x-line px-3 py-2 text-[15px] leading-5 outline-none focus:border-x-blue';
  var actions = document.createElement('div');
  actions.className = 'mt-2 flex items-center justify-end gap-2';
  var cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'rounded-full px-4 py-1.5 text-[15px] font-bold text-x-muted hover:bg-x-hover';
  cancel.textContent = 'Cancel';
  var save = document.createElement('button');
  save.type = 'submit';
  save.className = 'x-btn-blue h-9 px-4 text-[15px]';
  save.textContent = 'Save';
  var error = document.createElement('p');
  error.className = 'mt-2 hidden text-[13px] text-x-danger';
  actions.appendChild(cancel);
  actions.appendChild(save);
  editor.appendChild(area);
  editor.appendChild(actions);
  editor.appendChild(error);
  if (isAuthor && textEl) textEl.insertAdjacentElement('afterend', editor);

  function closeMenu() {
    menu.classList.add('hidden');
  }

  button.addEventListener('click', function (event) {
    event.stopPropagation();
    var willOpen = menu.classList.contains('hidden');
    document.querySelectorAll('[data-own-menu]').forEach(function (node) {
      node.classList.add('hidden');
    });
    if (!willOpen) return;
    menu.classList.remove('hidden');
    menu.classList.remove('top-full', 'bottom-full', 'mt-1', 'mb-1');
    var spaceBelow = window.innerHeight - button.getBoundingClientRect().bottom;
    if (spaceBelow < 96) {
      menu.classList.add('bottom-full', 'mb-1');
    } else {
      menu.classList.add('top-full', 'mt-1');
    }
  });
  menu.addEventListener('click', function (event) {
    event.stopPropagation();
  });

  editItem.addEventListener('click', function () {
    closeMenu();
    area.value = post.text || '';
    error.classList.add('hidden');
    if (textEl) textEl.classList.add('hidden');
    editor.classList.remove('hidden');
    area.focus();
  });

  cancel.addEventListener('click', function () {
    editor.classList.add('hidden');
    if (textEl && post.text) textEl.classList.remove('hidden');
  });

  editor.addEventListener('submit', function (event) {
    event.preventDefault();
    save.disabled = true;
    apiFetch('/posts/' + post.id + '/edit', {
      method: 'POST',
      body: JSON.stringify({ text: area.value.trim() }),
    })
      .then(function (result) {
        save.disabled = false;
        if (!result.ok) {
          error.classList.remove('hidden');
          error.textContent = result.data.message || 'Could not save that post.';
          return;
        }
        post.text = result.data.text || '';
        if (textEl) {
          textEl.textContent = post.text;
          textEl.classList.toggle('hidden', !post.text);
        }
        editor.classList.add('hidden');
      })
      .catch(function () {
        save.disabled = false;
        error.classList.remove('hidden');
        error.textContent = 'Cannot reach the server.';
      });
  });

  deleteItem.addEventListener('click', function () {
    closeMenu();
    openDialog({
      title: 'Delete post?',
      body: 'This can’t be undone. The post will be removed from your profile and the feed.',
      confirmLabel: 'Delete',
    }).then(function (ok) {
      if (!ok) return;
      apiFetch('/posts/' + post.id + '/delete', { method: 'POST', body: '{}' })
        .then(function (result) {
          if (!result.ok) {
            openDialog({
              title: 'Couldn’t delete post',
              body: result.data.message || 'Try again in a moment.',
            });
            return;
          }
          if (helpers.onDeleted) helpers.onDeleted(post);
        })
        .catch(function () {
          openDialog({
            title: 'Couldn’t delete post',
            body: 'Cannot reach the server.',
          });
        });
    });
  });

  wrap.appendChild(button);
  wrap.appendChild(menu);
  header.appendChild(wrap);
}

document.addEventListener('click', function () {
  document.querySelectorAll('[data-own-menu]').forEach(function (node) {
    node.classList.add('hidden');
  });
});

function mountCommentTools(copy, text, post, comment, paint, showError, allowEdit) {
  var tools = document.createElement('div');
  tools.className = 'mt-1 flex gap-3 text-[13px]';
  var editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'font-bold text-x-muted hover:text-x-blue';
  editBtn.textContent = 'Edit';
  var deleteBtn = document.createElement('button');
  deleteBtn.type = 'button';
  deleteBtn.className = 'font-bold text-x-muted hover:text-x-danger';
  deleteBtn.textContent = 'Delete';
  if (allowEdit !== false) tools.appendChild(editBtn);
  tools.appendChild(deleteBtn);

  var editor = document.createElement('form');
  editor.className = 'mt-2 hidden items-center gap-2';
  var field = document.createElement('input');
  field.type = 'text';
  field.maxLength = 280;
  field.className = 'h-9 min-w-0 flex-1 rounded-full bg-x-chip px-4 text-[15px] outline-none placeholder:text-x-muted focus:bg-x-panel focus:ring-1 focus:ring-x-blue';
  var save = document.createElement('button');
  save.type = 'submit';
  save.className = 'x-btn-blue h-8 shrink-0 px-3 text-[13px]';
  save.textContent = 'Save';
  var cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'shrink-0 text-[13px] font-bold text-x-muted hover:text-x-ink';
  cancel.textContent = 'Cancel';
  editor.appendChild(field);
  editor.appendChild(save);
  editor.appendChild(cancel);

  editBtn.addEventListener('click', function () {
    field.value = comment.text;
    text.classList.add('hidden');
    tools.classList.add('hidden');
    editor.classList.remove('hidden');
    editor.classList.add('flex');
    field.focus();
  });
  cancel.addEventListener('click', function () {
    editor.classList.add('hidden');
    editor.classList.remove('flex');
    text.classList.remove('hidden');
    tools.classList.remove('hidden');
  });
  editor.addEventListener('submit', function (event) {
    event.preventDefault();
    var next = field.value.trim();
    if (!next) {
      showError('Write a comment.');
      return;
    }
    save.disabled = true;
    apiFetch('/posts/' + post.id + '/comments/' + comment.id + '/edit', {
      method: 'POST',
      body: JSON.stringify({ text: next }),
    })
      .then(function (result) {
        save.disabled = false;
        if (!result.ok) {
          showError(result.data.message || 'Could not save that comment.');
          return;
        }
        applyPostUpdate(post, result.data);
        paint();
      })
      .catch(function () {
        save.disabled = false;
        showError('Cannot reach the server.');
      });
  });
  deleteBtn.addEventListener('click', function () {
    openDialog({
      title: 'Delete comment?',
      body: 'This can’t be undone and the reply will be removed.',
      confirmLabel: 'Delete',
    }).then(function (ok) {
      if (!ok) return;
      removeComment();
    });
  });

  function removeComment() {
    deleteBtn.disabled = true;
    apiFetch('/posts/' + post.id + '/comments/' + comment.id + '/delete', {
      method: 'POST',
      body: '{}',
    })
      .then(function (result) {
        deleteBtn.disabled = false;
        if (!result.ok) {
          showError(result.data.message || 'Could not delete that comment.');
          return;
        }
        applyPostUpdate(post, result.data);
        paint();
      })
      .catch(function () {
        deleteBtn.disabled = false;
        showError('Cannot reach the server.');
      });
  }

  copy.appendChild(tools);
  copy.appendChild(editor);
}

function mountPostActions(parent, post, helpers) {
  var row = document.createElement('div');
  row.className = 'mt-2 flex max-w-[425px] justify-between text-x-muted';

  var reply = document.createElement('button');
  reply.type = 'button';
  reply.className = 'action reply';
  reply.setAttribute('aria-label', 'Reply');
  reply.innerHTML = POST_ICONS.reply + '<span class="count"></span>';

  var repost = document.createElement('span');
  repost.className = 'action repost';
  repost.setAttribute('aria-hidden', 'true');
  repost.innerHTML = POST_ICONS.repost;

  var like = document.createElement('button');
  like.type = 'button';
  like.className = 'action like';
  like.setAttribute('aria-label', 'Like');
  like.innerHTML = POST_ICONS.like + '<span class="count"></span>';

  var share = document.createElement('span');
  share.className = 'action share';
  share.setAttribute('aria-hidden', 'true');
  share.innerHTML = POST_ICONS.share;

  row.appendChild(reply);
  row.appendChild(repost);
  row.appendChild(like);
  row.appendChild(share);
  parent.appendChild(row);

  var panel = document.createElement('div');
  panel.className = 'hidden pt-1';

  var list = document.createElement('div');
  var form = document.createElement('form');
  form.className = 'flex items-center gap-2 border-t border-x-line pt-3';
  var input = document.createElement('input');
  input.type = 'text';
  input.maxLength = 280;
  input.placeholder = 'Post your reply';
  input.className = 'h-10 min-w-0 flex-1 rounded-full bg-x-chip px-4 text-[15px] outline-none placeholder:text-x-muted focus:bg-x-panel focus:ring-1 focus:ring-x-blue';
  var submit = document.createElement('button');
  submit.type = 'submit';
  submit.className = 'x-btn-blue h-9 shrink-0 px-4 text-[15px]';
  submit.textContent = 'Reply';
  var notice = document.createElement('p');
  notice.className = 'mt-2 hidden text-[13px] text-x-danger';
  form.appendChild(input);
  form.appendChild(submit);
  var allowComment = !helpers || helpers.canComment !== false;
  panel.appendChild(list);
  if (allowComment) {
    panel.appendChild(form);
  } else {
    var locked = document.createElement('p');
    locked.className = 'border-t border-x-line pt-3 text-[13px] text-x-muted';
    locked.textContent = 'Only admins can comment in this group.';
    panel.appendChild(locked);
  }
  panel.appendChild(notice);
  parent.appendChild(panel);

  function paint() {
    var comments = post.comments || [];
    reply.querySelector('.count').textContent = comments.length ? String(comments.length) : '';
    like.classList.toggle('is-liked', !!post.liked);
    like.setAttribute('aria-pressed', post.liked ? 'true' : 'false');
    like.querySelector('.count').textContent = post.like_count ? String(post.like_count) : '';
    list.innerHTML = '';
    comments.forEach(function (comment) {
      var item = document.createElement('div');
      item.className = 'flex gap-3 border-b border-x-line py-3';
      var href = helpers.profileHref(comment.username, comment.email);
      var avatar = document.createElement('a');
      avatar.href = href;
      avatar.className = 'shrink-0';
      avatar.appendChild(helpers.picture(comment.photo, (comment.name || '?').charAt(0), 'size-8 text-xs'));
      var copy = document.createElement('div');
      copy.className = 'min-w-0 flex-1';
      var who = document.createElement('p');
      who.className = 'flex min-w-0 items-baseline gap-1 text-[15px]';
      var name = document.createElement('a');
      name.href = href;
      name.className = 'truncate font-bold hover:underline';
      name.textContent = comment.name;
      who.appendChild(name);
      if (comment.premium) who.appendChild(premiumMark());
      if (comment.username) {
        var handle = document.createElement('a');
        handle.href = href;
        handle.className = 'truncate text-x-muted hover:underline';
        handle.textContent = '@' + comment.username;
        who.appendChild(handle);
      }
      var text = document.createElement('p');
      text.className = 'text-[15px] leading-5 break-words whitespace-pre-wrap';
      text.textContent = comment.text;
      copy.appendChild(who);
      copy.appendChild(text);
      var ownsComment = !!(helpers.meEmail && comment.email === helpers.meEmail);
      if (ownsComment || helpers.canModerate) {
        mountCommentTools(copy, text, post, comment, paint, showError, ownsComment);
      }
      item.appendChild(avatar);
      item.appendChild(copy);
      list.appendChild(item);
    });
  }

  function showError(text) {
    notice.classList.remove('hidden');
    notice.textContent = text;
  }

  reply.addEventListener('click', function () {
    var open = panel.classList.toggle('hidden') === false;
    reply.classList.toggle('is-open', open);
    if (open) input.focus();
  });

  like.addEventListener('click', function () {
    like.disabled = true;
    apiFetch('/posts/' + post.id + '/like', { method: 'POST', body: '{}' })
      .then(function (result) {
        like.disabled = false;
        if (!result.ok) {
          panel.classList.remove('hidden');
          reply.classList.add('is-open');
          showError(result.data.message || 'Could not update that like.');
          return;
        }
        applyPostUpdate(post, result.data);
        paint();
      })
      .catch(function () {
        like.disabled = false;
        panel.classList.remove('hidden');
        reply.classList.add('is-open');
        showError('Cannot reach the server.');
      });
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) {
      showError('Write a comment.');
      return;
    }
    submit.disabled = true;
    apiFetch('/posts/' + post.id + '/comments', {
      method: 'POST',
      body: JSON.stringify({ text: text }),
    })
      .then(function (result) {
        submit.disabled = false;
        if (!result.ok) {
          showError(result.data.message || 'Could not post that reply.');
          return;
        }
        input.value = '';
        notice.classList.add('hidden');
        applyPostUpdate(post, result.data);
        paint();
      })
      .catch(function () {
        submit.disabled = false;
        showError('Cannot reach the server.');
      });
  });

  paint();
}

var POST_EMOJIS = ['😀', '😁', '😂', '😊', '😍', '😎', '🤔', '😭', '👍', '👏', '🙏', '🔥', '✨', '❤️', '🎉', '💯'];

function postImageProblem(file) {
  return imageFileProblem(file);
}

function mountPostMedia(parent, post, onVote) {
  var images = Array.isArray(post.images) && post.images.length ? post.images : [];
  if (!images.length && post.image) images = [post.image];
  if (images.length) {
    var grid = document.createElement('div');
    grid.className = 'mt-3 grid gap-0.5 overflow-hidden rounded-2xl border border-x-line ' + (images.length === 1 ? 'grid-cols-1' : 'grid-cols-2');
    images.forEach(function (src, index) {
      var img = document.createElement('img');
      img.src = API + src;
      img.alt = '';
      img.className = 'w-full object-cover';
      if (images.length === 1) img.className += ' max-h-[510px]';
      else if (images.length === 3 && index === 0) img.className += ' col-span-2 max-h-80';
      else img.className += ' h-40 sm:h-56';
      grid.appendChild(img);
    });
    parent.appendChild(grid);
  }

  if (!post.poll || !Array.isArray(post.poll.options) || !post.poll.options.length) return;
  var voted = typeof post.poll.choice === 'number';
  var box = document.createElement('div');
  box.className = 'mt-3 overflow-hidden rounded-2xl border border-x-line';
  post.poll.options.forEach(function (option, index) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'relative block w-full px-3 py-2.5 text-left text-[15px] hover:bg-x-hover';
    if (voted) {
      var bar = document.createElement('span');
      bar.className = 'absolute inset-y-0 left-0 ' + (index === post.poll.choice ? 'bg-x-blue/20' : 'bg-x-hover');
      bar.style.width = (option.percent || 0) + '%';
      var label = document.createElement('span');
      label.className = 'relative flex items-center justify-between gap-3';
      var name = document.createElement('span');
      if (index === post.poll.choice) name.className = 'font-bold';
      name.textContent = option.text;
      var pct = document.createElement('span');
      pct.className = 'text-[13px] text-x-muted';
      pct.textContent = (option.percent || 0) + '%';
      label.appendChild(name);
      label.appendChild(pct);
      button.appendChild(bar);
      button.appendChild(label);
    } else {
      button.textContent = option.text;
    }
    button.addEventListener('click', function () {
      if (typeof onVote !== 'function') return;
      button.disabled = true;
      apiFetch('/posts/' + post.id + '/vote', {
        method: 'POST',
        body: JSON.stringify({ choice: index }),
      }).then(function (result) {
        button.disabled = false;
        if (result.ok) onVote(result.data);
      }).catch(function () {
        button.disabled = false;
      });
    });
    box.appendChild(button);
  });
  var total = document.createElement('p');
  total.className = 'border-t border-x-line px-3 py-2 text-[13px] text-x-muted';
  var count = post.poll.total || 0;
  total.textContent = count === 1 ? '1 vote' : count + ' votes';
  box.appendChild(total);
  parent.appendChild(box);
}

function bindPostComposer(preview, tools, textarea, hooks) {
  hooks = hooks || {};
  var sources = [];
  var files = [];
  var edited = [];
  var sizing = Promise.resolve();
  var fitToken = 0;
  var pollOpen = false;
  var choiceValues = ['', ''];
  var urls = [];

  var fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/jpeg,image/png,image/gif,image/webp';
  fileInput.multiple = true;
  fileInput.className = 'sr-only';

  function iconButton(label, svg, tint) {
    var button = document.createElement('button');
    button.type = 'button';
    if (hooks.darkTools) {
      button.className = 'z-tool-chip';
      if (tint) button.style.color = tint;
    } else {
      button.className = 'inline-flex size-9 items-center justify-center rounded-full text-x-blue hover:bg-x-blue/10';
    }
    button.setAttribute('aria-label', label);
    button.title = label;
    button.innerHTML = svg;
    return button;
  }

  var photoButton = iconButton('Photo', '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.3"/><path stroke-linecap="round" stroke-linejoin="round" d="m21 15.5-4.2-4.2L8 19"/></svg>', '#1d9bf0');
  var emojiButton = iconButton('Emoji', '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path stroke-linecap="round" d="M8.5 14.2c.9 1.1 2.1 1.6 3.5 1.6s2.6-.5 3.5-1.6"/><path stroke-linecap="round" d="M9 10h.01M15 10h.01"/></svg>', '#f7b928');
  var pollButton = iconButton('Poll', '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M5 19V10"/><path d="M12 19V5"/><path d="M19 19v-7"/></svg>', '#00ba7c');
  if (hooks.darkTools) {
    photoButton.insertAdjacentHTML('beforeend', '<span>Photo</span>');
    emojiButton.insertAdjacentHTML('beforeend', '<span>Emoji</span>');
    pollButton.insertAdjacentHTML('beforeend', '<span>Poll</span>');
  }

  var emojiPop = document.createElement('div');
  emojiPop.className = 'absolute bottom-12 left-0 z-20 hidden w-56 rounded-2xl border border-x-line bg-x-panel p-2 shadow-xl';
  var emojiGrid = document.createElement('div');
  emojiGrid.className = 'grid grid-cols-8 gap-1';
  POST_EMOJIS.forEach(function (symbol) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'inline-flex size-7 items-center justify-center rounded-lg text-lg hover:bg-x-hover';
    button.textContent = symbol;
    button.addEventListener('click', function () {
      var start = textarea.selectionStart || textarea.value.length;
      var end = textarea.selectionEnd || textarea.value.length;
      textarea.value = textarea.value.slice(0, start) + symbol + textarea.value.slice(end);
      var next = start + symbol.length;
      textarea.focus();
      if (textarea.setSelectionRange) textarea.setSelectionRange(next, next);
      emojiPop.classList.add('hidden');
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    });
    emojiGrid.appendChild(button);
  });
  emojiPop.appendChild(emojiGrid);

  tools.classList.add('relative');
  tools.appendChild(fileInput);
  tools.appendChild(photoButton);
  tools.appendChild(emojiButton);
  tools.appendChild(pollButton);
  tools.appendChild(emojiPop);

  function filledChoices() {
    return choiceValues.map(function (value) { return value.trim(); }).filter(Boolean);
  }

  function notify() {
    if (typeof hooks.onChange === 'function') hooks.onChange();
  }

  function notice(text) {
    if (text && typeof hooks.onNotice === 'function') hooks.onNotice(text);
  }

  function dropUrls() {
    urls.forEach(function (url) { URL.revokeObjectURL(url); });
    urls = [];
  }

  function fitPhotos() {
    var token = fitToken + 1;
    fitToken = token;
    sizing = Promise.all(sources.map(function (file, index) {
      if (edited[index] && files[index]) return Promise.resolve(files[index]);
      return resizeImageFile(file, 1600);
    })).then(function (next) {
      if (token !== fitToken) return;
      files = next;
      paint();
      notify();
    });
    return sizing;
  }

  function cropAt(index) {
    var source = sources[index];
    if (!source || imageKind(source) === 'image/gif') return;
    openImageCrop(source, { title: 'Crop', aspects: POST_CROP_ASPECTS }).then(function (file) {
      var still = sources.indexOf(source);
      if (!file || still < 0) return;
      files[still] = file;
      edited[still] = true;
      paint();
      notify();
    });
  }

  function paint() {
    dropUrls();
    preview.innerHTML = '';
    if (files.length) {
      var grid = document.createElement('div');
      grid.className = 'mt-2 grid gap-1 ' + (files.length === 1 ? 'grid-cols-1' : 'grid-cols-2');
      files.forEach(function (file, index) {
        var url = URL.createObjectURL(file);
        urls.push(url);
        var tile = document.createElement('div');
        tile.className = 'relative overflow-hidden rounded-2xl border border-x-line';
        var img = document.createElement('img');
        img.src = url;
        img.alt = '';
        img.className = files.length === 1 ? 'max-h-[420px] w-full object-contain bg-black' : 'h-40 w-full object-cover sm:h-48';
        tile.appendChild(img);
        if (imageKind(sources[index]) !== 'image/gif') {
          var crop = makeCropButton();
          crop.addEventListener('click', function () { cropAt(index); });
          tile.appendChild(crop);
        }
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'absolute right-2 top-2 inline-flex size-7 items-center justify-center rounded-full bg-black/70 text-sm font-bold text-white';
        remove.setAttribute('aria-label', 'Remove photo');
        remove.textContent = '×';
        remove.addEventListener('click', function () {
          sources.splice(index, 1);
          files.splice(index, 1);
          edited.splice(index, 1);
          paint();
          notify();
        });
        tile.appendChild(remove);
        grid.appendChild(tile);
      });
      preview.appendChild(grid);
    }

    if (!pollOpen) return;
    var panel = document.createElement('div');
    panel.className = 'mt-2 rounded-2xl border border-x-line p-3';
    choiceValues.forEach(function (value, index) {
      var row = document.createElement('div');
      row.className = 'mb-2 flex items-center gap-2';
      var input = document.createElement('input');
      input.type = 'text';
      input.maxLength = 40;
      input.value = value;
      input.placeholder = 'Choice ' + (index + 1);
      input.className = 'h-10 min-w-0 flex-1 rounded-xl border border-x-border px-3 text-[15px] outline-none focus:border-x-blue';
      input.addEventListener('input', function () {
        choiceValues[index] = input.value;
        notify();
      });
      row.appendChild(input);
      if (choiceValues.length > 2) {
        var removeChoice = document.createElement('button');
        removeChoice.type = 'button';
        removeChoice.className = 'inline-flex size-8 shrink-0 items-center justify-center rounded-full text-x-muted hover:bg-x-hover';
        removeChoice.setAttribute('aria-label', 'Remove choice');
        removeChoice.textContent = '×';
        removeChoice.addEventListener('click', function () {
          choiceValues.splice(index, 1);
          paint();
          notify();
        });
        row.appendChild(removeChoice);
      }
      panel.appendChild(row);
    });
    var actions = document.createElement('div');
    actions.className = 'flex items-center justify-between';
    if (choiceValues.length < 4) {
      var add = document.createElement('button');
      add.type = 'button';
      add.className = 'text-[13px] font-bold text-x-blue';
      add.textContent = 'Add choice';
      add.addEventListener('click', function () {
        choiceValues.push('');
        paint();
      });
      actions.appendChild(add);
    } else {
      actions.appendChild(document.createElement('span'));
    }
    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'text-[13px] font-bold text-x-muted';
    close.textContent = 'Remove poll';
    close.addEventListener('click', function () {
      pollOpen = false;
      choiceValues = ['', ''];
      paint();
      notify();
    });
    actions.appendChild(close);
    panel.appendChild(actions);
    preview.appendChild(panel);
  }

  photoButton.addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () {
    var picked = Array.prototype.slice.call(fileInput.files || []);
    fileInput.value = '';
    var added = [];
    picked.forEach(function (file) {
      var problem = postImageProblem(file);
      if (problem) {
        notice(problem);
        return;
      }
      if (sources.length >= 4) {
        notice('A post can have 4 photos at most.');
        return;
      }
      if (pollOpen) {
        pollOpen = false;
        choiceValues = ['', ''];
        notice('The poll was cleared so these photos can be added.');
      }
      sources.push(file);
      edited.push(false);
      added.push(sources.length - 1);
    });
    fitPhotos().then(function () {
      if (added.length === 1 && imageKind(sources[added[0]]) !== 'image/gif') cropAt(added[0]);
    });
  });

  emojiButton.addEventListener('click', function () {
    emojiPop.classList.toggle('hidden');
  });
  document.addEventListener('click', function (event) {
    if (!tools.contains(event.target)) emojiPop.classList.add('hidden');
  });

  pollButton.addEventListener('click', function () {
    if (sources.length) {
      sources = [];
      files = [];
      edited = [];
      notice('The photos were cleared so a poll can be added.');
    }
    pollOpen = true;
    paint();
    notify();
  });

  return {
    ready: function (text) {
      return !!(String(text || '').trim() || sources.length || (pollOpen && filledChoices().length >= 2));
    },
    whenReady: function () {
      return sizing;
    },
    problem: function () {
      if (!pollOpen) return '';
      var filled = filledChoices();
      if (filled.length === 0) return '';
      if (filled.length < 2) return 'A poll needs at least 2 choices.';
      return '';
    },
    fill: function (form) {
      files.forEach(function (file) { form.append('image', file); });
      var filled = filledChoices();
      if (pollOpen && filled.length >= 2) form.append('poll', JSON.stringify(filled));
    },
    clear: function () {
      sources = [];
      files = [];
      edited = [];
      pollOpen = false;
      choiceValues = ['', ''];
      fileInput.value = '';
      emojiPop.classList.add('hidden');
      paint();
      notify();
    },
  };
}
