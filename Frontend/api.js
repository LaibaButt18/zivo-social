var API = "http://127.0.0.1:5000";
var authRedirecting = false;

function getToken() {
  return localStorage.getItem("zivo_token") || "";
}

function authHeaders() {
  var headers = { "Content-Type": "application/json" };
  var token = getToken();
  if (token) {
    headers.Authorization = "Bearer " + token;
  }
  return headers;
}

function tokenLooksExpired(token) {
  if (!token) return false;
  try {
    var parts = token.split(".");
    if (parts.length < 2) return false;
    var json = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    while (json.length % 4) json += "=";
    var payload = JSON.parse(atob(json));
    if (!payload.exp) return false;
    return payload.exp * 1000 <= Date.now();
  } catch (err) {
    return false;
  }
}

function authNoticeText(reason) {
  if (reason === "expired") return "Your session expired. Please sign in again.";
  if (reason === "logout") return "You were signed out.";
  if (reason === "required") return "Please sign in to continue.";
  return "";
}

function redirectToLogin(reason) {
  if (authRedirecting) return;
  authRedirecting = true;
  clearToken();
  var path = window.location.pathname || "";
  if (/loginpage\.html$/.test(path) || /login\.html$/.test(path)) {
    authRedirecting = false;
    showAuthNotice(reason);
    return;
  }
  var query = reason ? ("?reason=" + encodeURIComponent(reason)) : "";
  window.location.href = "loginpage.html" + query;
}

function showAuthNotice(reason) {
  var notice = document.getElementById("notice");
  if (!notice) return;
  var text = authNoticeText(reason || new URLSearchParams(window.location.search).get("reason"));
  if (!text) return;
  notice.classList.remove("hidden");
  notice.className = "text-[15px] leading-5 text-x-ink";
  notice.setAttribute("role", "status");
  notice.textContent = text;
}

function maybeHandleUnauthorized(result, token, options) {
  options = options || {};
  if (!result || result.status !== 401 || options.skipAuthRedirect) return result;
  if (!token) return result;
  var reason = (result.data && result.data.reason) || (tokenLooksExpired(token) ? "expired" : "required");
  redirectToLogin(reason);
  return result;
}

function apiFetch(path, options) {
  options = options || {};
  var token = getToken();
  options.headers = authHeaders();
  return fetch(API + path, options).then(function (response) {
    return response.text().then(function (text) {
      var data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (err) {
          data = { message: "The server could not complete that request." };
        }
      }
      return maybeHandleUnauthorized(
        { ok: response.ok, status: response.status, data: data },
        token,
        options
      );
    });
  });
}

function apiForm(path, formData, options) {
  options = options || {};
  var headers = {};
  var token = getToken();
  if (token) {
    headers.Authorization = "Bearer " + token;
  }
  return fetch(API + path, {
    method: "POST",
    headers: headers,
    body: formData,
  }).then(function (response) {
    return response.text().then(function (text) {
      var data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (err) {
          data = { message: "The server could not complete that request." };
        }
      }
      return maybeHandleUnauthorized(
        { ok: response.ok, status: response.status, data: data },
        token,
        options
      );
    });
  });
}

function saveToken(data) {
  if (data && data.token) {
    localStorage.setItem("zivo_token", data.token);
  }
}

function clearToken() {
  localStorage.removeItem("zivo_token");
}

function requireAuth() {
  if (!getToken()) {
    redirectToLogin("required");
    return false;
  }
  if (tokenLooksExpired(getToken())) {
    redirectToLogin("expired");
    return false;
  }
  return true;
}

function requireGuest() {
  if (!getToken()) {
    showAuthNotice();
    return Promise.resolve(false);
  }
  return apiFetch("/me", { skipAuthRedirect: true }).then(function (result) {
    if (result.ok) {
      window.location.replace("feed.html");
      return true;
    }
    var reason = (result.data && result.data.reason) || (tokenLooksExpired(getToken()) ? "expired" : "required");
    clearToken();
    showAuthNotice(reason);
    return false;
  }).catch(function () {
    showAuthNotice();
    return false;
  });
}

function signOut() {
  return apiFetch("/logout", { method: "POST", body: "{}", skipAuthRedirect: true })
    .catch(function () { return null; })
    .finally(function () {
      redirectToLogin("logout");
    });
}

function premiumMark() {
  var mark = document.createElement("span");
  mark.className = "inline-flex shrink-0 text-x-blue";
  mark.title = "Zivo Premium";
  mark.setAttribute("aria-label", "Premium");
  mark.innerHTML = '<svg viewBox="0 0 24 24" class="size-4" aria-hidden="true"><path fill="currentColor" d="M12 2.4 9.6 8.2 3.3 8.8l4.8 4.1-1.4 6.3L12 16.2l5.3 3 1.4-6.3 4.8-4.1-6.3-.6z"/></svg>';
  return mark;
}

var userDirectoryPromise = null;
var userSearchDismissBound = false;
var userSearchSeq = 0;

function loadUserDirectory() {
  if (!userDirectoryPromise) {
    userDirectoryPromise = apiFetch("/users").then(function (result) {
      if (result.status === 401) {
        return { ok: false, people: [] };
      }
      if (!result.ok || !Array.isArray(result.data)) {
        userDirectoryPromise = null;
        return { ok: false, people: [] };
      }
      return { ok: true, people: result.data };
    }).catch(function () {
      userDirectoryPromise = null;
      return { ok: false, people: [] };
    });
  }
  return userDirectoryPromise;
}

function bindUserSearchDismiss() {
  if (userSearchDismissBound) return;
  userSearchDismissBound = true;
  document.addEventListener("mousedown", function (event) {
    var nodes = document.querySelectorAll("[data-user-search]");
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].contains(event.target)) continue;
      if (nodes[i]._closeUserSearch) nodes[i]._closeUserSearch();
    }
  });
}

function userAvatar(person, sizeClass) {
  var letter = ((person && person.name) || "?").charAt(0).toUpperCase();
  if (person && person.photo) {
    var img = document.createElement("img");
    img.src = API + person.photo;
    img.alt = "";
    img.className = "shrink-0 rounded-full object-cover " + sizeClass;
    return img;
  }
  var fallback = document.createElement("span");
  var letterSize = sizeClass.indexOf("text-") === -1 ? "text-sm " : "";
  fallback.className = "flex shrink-0 items-center justify-center rounded-full bg-x-blue font-bold text-white " + letterSize + sizeClass;
  fallback.textContent = letter;
  return fallback;
}

function mountUserSearch(container, options) {
  options = options || {};
  bindUserSearchDismiss();
  var seq = userSearchSeq++;
  var listId = "user-search-" + seq;
  var selected = [];
  var people = [];
  var loaded = false;
  var failed = false;
  var open = false;
  var active = -1;
  var busy = false;
  var pendingEmail = "";
  var query = "";
  var visible = [];

  var root = document.createElement("div");
  root.setAttribute("data-user-search", "");
  root.className = (options.inset === false ? "" : "px-3 py-3") + (options.divided ? " border-b border-x-line" : "");

  var fullNote = document.createElement("p");
  fullNote.className = "hidden text-[15px] text-x-muted";
  fullNote.textContent = "This chat already has 32 people.";

  var chips = document.createElement("div");
  chips.className = "mb-2 hidden flex-wrap gap-2";

  var field = document.createElement("div");
  field.className = "relative";
  var icon = document.createElement("span");
  icon.className = "pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-x-muted";
  icon.innerHTML = '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path stroke-linecap="round" d="m16 16 4 4"/></svg>';
  var input = document.createElement("input");
  input.type = "text";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", listId);
  input.placeholder = options.placeholder || "Search people";
  input.className = "h-10 w-full rounded-full border border-transparent bg-x-chip pr-3 pl-10 text-[15px] outline-none placeholder:text-x-muted focus:border-x-blue focus:bg-x-panel focus:ring-1 focus:ring-x-blue";
  field.appendChild(icon);
  field.appendChild(input);

  var results = document.createElement("div");
  results.id = listId;
  results.setAttribute("data-user-results", "");
  results.setAttribute("role", "listbox");
  results.className = "menu-pop mt-2 hidden max-h-64 overflow-y-auto overscroll-contain rounded-2xl border border-x-line bg-x-panel";

  var error = document.createElement("p");
  error.className = "mt-2 hidden text-[13px] text-x-danger";
  error.setAttribute("role", "status");

  root.appendChild(fullNote);
  root.appendChild(chips);
  root.appendChild(field);
  root.appendChild(results);
  root.appendChild(error);
  container.appendChild(root);

  function showError(text) {
    if (!text) {
      error.classList.add("hidden");
      error.textContent = "";
      return;
    }
    error.classList.remove("hidden");
    error.textContent = text;
  }

  function isFull() {
    return !!(options.isFull && options.isFull());
  }

  function excludedMap() {
    var raw = typeof options.exclude === "function" ? options.exclude() : (options.exclude || []);
    var map = {};
    if (Array.isArray(raw)) {
      raw.forEach(function (email) { if (email) map[email] = true; });
    } else if (raw) {
      Object.keys(raw).forEach(function (email) { map[email] = true; });
    }
    selected.forEach(function (person) { map[person.email] = true; });
    return map;
  }

  function rankPerson(person) {
    var q = query.toLowerCase();
    var name = (person.name || "").toLowerCase();
    var username = (person.username || "").toLowerCase();
    var email = (person.email || "").toLowerCase();
    if (!q) return 1;
    if (name.indexOf(q) === 0 || username.indexOf(q) === 0) return 0;
    if (name.indexOf(q) !== -1 || username.indexOf(q) !== -1 || email.indexOf(q) !== -1) return 2;
    return -1;
  }

  function paintChips() {
    chips.innerHTML = "";
    chips.className = selected.length ? "mb-2 flex flex-wrap gap-2" : "hidden";
    selected.forEach(function (person) {
      var chip = document.createElement("span");
      chip.className = "inline-flex max-w-full items-center gap-1 rounded-full bg-x-chip py-1 pr-1 pl-1";
      chip.appendChild(userAvatar(person, "size-6 text-xs"));
      var label = document.createElement("span");
      label.className = "max-w-[10rem] truncate text-[13px] font-bold";
      label.textContent = person.name || person.username || person.email;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "inline-flex size-6 shrink-0 items-center justify-center rounded-full text-x-muted hover:bg-x-hover hover:text-x-ink";
      remove.setAttribute("aria-label", "Remove " + label.textContent);
      remove.innerHTML = '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" d="M6 6l12 12M18 6 6 18"/></svg>';
      remove.addEventListener("click", function () {
        selected = selected.filter(function (item) { return item.email !== person.email; });
        showError("");
        paintChips();
        renderList();
        if (options.onChange) options.onChange(selected.slice());
      });
      chip.appendChild(label);
      chip.appendChild(remove);
      chips.appendChild(chip);
    });
  }

  function noteRow(text) {
    var row = document.createElement("p");
    row.className = "px-3 py-3 text-[15px] text-x-muted";
    row.textContent = text;
    results.appendChild(row);
  }

  function personRow(person, index, already) {
    var row = document.createElement("button");
    row.type = "button";
    row.id = listId + "-opt-" + index;
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", index === active ? "true" : "false");
    row.disabled = busy || already;
    row.className = "flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-x-hover disabled:cursor-default disabled:hover:bg-transparent" + (index === active && !already ? " bg-x-hover" : "");
    row.appendChild(userAvatar(person, "size-9"));
    var copy = document.createElement("span");
    copy.className = "min-w-0 flex-1";
    var nameLine = document.createElement("span");
    nameLine.className = "flex min-w-0 items-center gap-1";
    var name = document.createElement("span");
    name.className = "truncate text-[15px] font-bold";
    name.textContent = person.name || "Someone";
    nameLine.appendChild(name);
    if (person.premium) nameLine.appendChild(premiumMark());
    var handle = document.createElement("span");
    handle.className = "block truncate text-[13px] text-x-muted";
    handle.textContent = person.username ? "@" + person.username : (person.email || "");
    copy.appendChild(nameLine);
    copy.appendChild(handle);
    row.appendChild(copy);
    var action = document.createElement("span");
    action.className = already
      ? "shrink-0 text-[13px] font-bold text-x-muted"
      : "inline-flex h-7 shrink-0 items-center rounded-full bg-x-blue px-3 text-[13px] font-bold text-white";
    action.textContent = already ? "Added" : (busy && person.email === pendingEmail ? "Adding…" : "Add");
    row.appendChild(action);
    if (!already) {
      row.addEventListener("click", function () {
        choose(person);
      });
      row.addEventListener("mouseenter", function () {
        if (busy) return;
        active = index;
        paintActive();
      });
    }
    return row;
  }

  function paintActive() {
    var rows = results.querySelectorAll("[role='option']");
    for (var i = 0; i < rows.length; i++) {
      var on = rows[i].id === listId + "-opt-" + active;
      rows[i].setAttribute("aria-selected", on ? "true" : "false");
      rows[i].classList.toggle("bg-x-hover", on);
    }
    input.setAttribute("aria-activedescendant", active >= 0 ? listId + "-opt-" + active : "");
    var current = results.querySelector('[aria-selected="true"]');
    if (current && current.scrollIntoView) current.scrollIntoView({ block: "nearest" });
  }

  function renderList() {
    if (isFull()) {
      fullNote.classList.remove("hidden");
      field.classList.add("hidden");
      results.classList.add("hidden");
      chips.classList.add("hidden");
      return;
    }
    fullNote.classList.add("hidden");
    field.classList.remove("hidden");
    results.innerHTML = "";
    input.setAttribute("aria-expanded", open ? "true" : "false");
    results.classList.toggle("hidden", !open);
    if (!open) return;

    if (!loaded && !failed) {
      noteRow("Looking up people…");
      return;
    }
    if (failed) {
      noteRow("Could not load people. Try again.");
      return;
    }

    var skip = excludedMap();
    var addable = [];
    var present = [];
    people.forEach(function (person) {
      var rank = rankPerson(person);
      if (rank < 0) return;
      if (skip[person.email]) present.push(person);
      else addable.push({ person: person, rank: rank });
    });
    addable.sort(function (a, b) {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return (a.person.name || "").toLowerCase().localeCompare((b.person.name || "").toLowerCase());
    });
    visible = addable.slice(0, 8).map(function (item) { return item.person; });
    if (active >= visible.length) active = visible.length - 1;

    if (!query && visible.length) {
      var heading = document.createElement("p");
      heading.className = "px-3 pt-2 text-[13px] font-bold text-x-muted";
      heading.textContent = "People";
      results.appendChild(heading);
    }
    if (!visible.length && query && present.length) {
      present.slice(0, 4).forEach(function (person, index) {
        results.appendChild(personRow(person, "added-" + index, true));
      });
      return;
    }
    if (!visible.length) {
      noteRow(query ? "No people match that search." : "No one else to add.");
      return;
    }
    visible.forEach(function (person, index) {
      results.appendChild(personRow(person, index, false));
    });
  }

  function choose(person) {
    if (busy || !person) return;
    if (options.multiple) {
      if (selected.some(function (item) { return item.email === person.email; })) return;
      if (options.max && selected.length >= options.max) {
        showError(options.maxMessage || "A chat can have 32 people at most.");
        return;
      }
      selected.push(person);
      query = "";
      input.value = "";
      active = 0;
      showError("");
      paintChips();
      renderList();
      input.focus();
      if (options.onChange) options.onChange(selected.slice());
      return;
    }
    if (!options.onSelect) return;
    busy = true;
    pendingEmail = person.email;
    showError("");
    renderList();
    Promise.resolve(options.onSelect(person)).then(function (result) {
      busy = false;
      if (!root.isConnected) return;
      if (result && result.ok === false) {
        showError((result.data && result.data.message) || "Could not add that person.");
        renderList();
        return;
      }
      query = "";
      input.value = "";
      active = -1;
      renderList();
    }).catch(function () {
      busy = false;
      if (!root.isConnected) return;
      showError("Cannot reach the server.");
      renderList();
    });
  }

  function ensurePeople() {
    loadUserDirectory().then(function (result) {
      if (!root.isConnected) return;
      loaded = !!result.ok;
      failed = !result.ok;
      people = result.people || [];
      renderList();
    });
  }

  root._closeUserSearch = function () {
    if (!open) return;
    open = false;
    active = -1;
    renderList();
  };

  input.addEventListener("focus", function () {
    if (isFull()) return;
    open = true;
    showError("");
    if (!loaded) ensurePeople();
    renderList();
  });
  input.addEventListener("input", function () {
    query = input.value.trim();
    active = -1;
    open = true;
    showError("");
    renderList();
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      open = true;
      renderList();
      if (!visible.length) return;
      active = Math.min(visible.length - 1, active + 1);
      paintActive();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      open = true;
      renderList();
      if (!visible.length) return;
      active = active <= 0 ? 0 : active - 1;
      paintActive();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      open = false;
      active = -1;
      renderList();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (active >= 0 && visible[active]) choose(visible[active]);
      else if (visible.length === 1) choose(visible[0]);
      else {
        open = true;
        renderList();
      }
    }
  });

  ensurePeople();
  paintChips();
  renderList();

  return {
    getSelected: function () { return selected.slice(); },
    clear: function () {
      selected = [];
      query = "";
      input.value = "";
      active = -1;
      open = false;
      showError("");
      paintChips();
      renderList();
    },
  };
}

function refreshNotifyBadge() {
  if (!localStorage.getItem("zivo_token")) return;
  var links = document.querySelectorAll('[data-nav="notifications"]');
  if (!links.length) return;
  apiFetch("/notifications/unread").then(function (result) {
    if (!result.ok) return;
    var count = result.data.unread || 0;
    links.forEach(function (link) {
      var badge = link.querySelector("[data-notify-count]");
      var host = link.querySelector(".z-top-glyph") || link;
      if (!badge) {
        badge = document.createElement("span");
        badge.setAttribute("data-notify-count", "");
        badge.className = "notify-count";
        host.appendChild(badge);
      } else if (badge.parentNode !== host) {
        host.appendChild(badge);
      }
      if (count > 0) {
        badge.textContent = count > 9 ? "9+" : String(count);
        badge.classList.remove("hidden");
      } else {
        badge.textContent = "";
        badge.classList.add("hidden");
      }
    });
  }).catch(function () {});
}

document.addEventListener("DOMContentLoaded", refreshNotifyBadge);
