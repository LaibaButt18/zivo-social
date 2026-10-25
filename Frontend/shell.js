/* Shared dark app chrome: top bar, rails, account menu, badges. */
(function () {
  var STOP = {
    a: 1, an: 1, the: 1, and: 1, or: 1, but: 1, if: 1, in: 1, on: 1, at: 1, to: 1, for: 1,
    of: 1, is: 1, it: 1, as: 1, be: 1, by: 1, this: 1, that: 1, with: 1, from: 1, are: 1,
    was: 1, were: 1, you: 1, your: 1, me: 1, my: 1, we: 1, our: 1, they: 1, them: 1, their: 1,
    i: 1, im: 1, ive: 1, its: 1, just: 1, like: 1, so: 1, not: 1, no: 1, yes: 1, do: 1, did: 1,
    have: 1, has: 1, had: 1, will: 1, can: 1, all: 1, about: 1, what: 1, when: 1, how: 1,
  };

  var ICONS = {
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.4 12 4.2l7.5 6.2V19a1.5 1.5 0 0 1-1.5 1.5H15v-5.2H9V20.5H6A1.5 1.5 0 0 1 4.5 19z"/></svg>',
    chats: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6.2 7.2h11.6A1.6 1.6 0 0 1 19.4 8.8v6a1.6 1.6 0 0 1-1.6 1.6H9.4L6.2 19.2v-2.8A1.6 1.6 0 0 1 4.6 14.8v-6a1.6 1.6 0 0 1 1.6-1.6z"/></svg>',
    notes: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6.4 9.2a5.6 5.6 0 0 1 11.2 0c0 4.2 1.3 5.6 1.3 5.6H5.1s1.3-1.4 1.3-5.6z"/><path stroke-linecap="round" d="M10 18.2a2 2 0 0 0 4 0"/></svg>',
    blogs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5.2 5.2h4.4A2.4 2.4 0 0 1 12 7.6v11.2a2 2 0 0 0-2-2H5.2z"/><path stroke-linecap="round" stroke-linejoin="round" d="M18.8 5.2h-4.4A2.4 2.4 0 0 0 12 7.6v11.2a2 2 0 0 1 2-2h4.8z"/></svg>',
    more: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/></svg>',
    groups: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" d="M15.2 19.2v-1c0-1.8-1.8-3.2-4-3.2s-4 1.4-4 3.2v1"/><circle cx="11.2" cy="8.3" r="2.6"/><path stroke-linecap="round" d="M18.8 19.2v-.8c0-1.3-1-2.4-2.3-2.8"/><circle cx="16.6" cy="9.2" r="2"/></svg>',
    webinars: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3.4" y="6.6" width="11.2" height="8.2" rx="1.8"/><path stroke-linecap="round" stroke-linejoin="round" d="m14.6 9.8 5.2-2.3v6.4l-5.2-2.3"/></svg>',
    profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="8.4" r="2.8"/><path stroke-linecap="round" d="M6.2 19.1c1.2-2.5 3.3-3.8 5.8-3.8s4.6 1.3 5.8 3.8"/></svg>',
    premium: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2.4 9.6 8.2 3.3 8.8l4.8 4.1-1.4 6.3L12 16.2l5.3 3 1.4-6.3 4.8-4.1-6.3-.6z"/></svg>',
    search: '<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path stroke-linecap="round" d="m16 16 4 4"/></svg>',
  };

  function el(tag, className, html) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (html != null) node.innerHTML = html;
    return node;
  }

  function picture(src, letter, sizeClass) {
    if (src) {
      var img = document.createElement("img");
      img.src = (typeof API !== "undefined" ? API : "") + src;
      img.alt = "";
      img.className = "shrink-0 rounded-full object-cover " + sizeClass;
      return img;
    }
    var fallback = document.createElement("span");
    fallback.className =
      "flex shrink-0 items-center justify-center rounded-full bg-x-blue text-sm font-bold text-white " +
      sizeClass;
    fallback.textContent = (letter || "?").toUpperCase();
    return fallback;
  }

  function profileHref(username, email) {
    var key = username || email || "";
    if (!key) return "profile.html";
    return "profile.html?user=" + encodeURIComponent(key);
  }

  function fillTopbar(root, nav) {
    root.innerHTML = "";
    var brand = el("a", "z-topbar-brand");
    brand.href = "feed.html";
    brand.setAttribute("aria-label", "Zivo");
    brand.innerHTML =
      '<img src="./assets/logo-mark.svg" alt="" class="size-8 shrink-0"><span>Zivo</span>';
    root.appendChild(brand);

    var searchWrap = el("div", "z-topbar-search");
    searchWrap.innerHTML =
      '<span class="z-topbar-search-icon">' +
      ICONS.search +
      "</span>" +
      '<input id="shellSearch" type="search" placeholder="Explore" autocomplete="off">';
    root.appendChild(searchWrap);

    var navBar = el("nav", "z-topbar-nav", "");
    navBar.setAttribute("aria-label", "Primary");

    function topLink(key, href, label, icon) {
      var a = el("a", "z-top-link");
      a.href = href;
      a.dataset.shellNav = key;
      if (key === "notifications") a.dataset.nav = "notifications";
      if (key === nav) a.setAttribute("aria-current", "page");
      a.setAttribute("aria-label", label);
      a.innerHTML = icon + "<span>" + label + "</span>";
      return a;
    }

    navBar.appendChild(topLink("home", "feed.html", "Home", ICONS.home));
    navBar.appendChild(topLink("chats", "chats.html", "Chats", ICONS.chats));
    navBar.appendChild(topLink("notifications", "notifications.html", "Notifications", ICONS.notes));
    navBar.appendChild(topLink("blogs", "blogs.html", "Blogs", ICONS.blogs));

    var moreWrap = el("div", "z-top-more");
    var moreBtn = el("button", "z-top-link");
    moreBtn.type = "button";
    moreBtn.id = "shellMoreToggle";
    moreBtn.setAttribute("aria-label", "More");
    moreBtn.setAttribute("aria-expanded", "false");
    moreBtn.innerHTML = ICONS.more + "<span>More</span>";
    if (nav === "groups" || nav === "webinars" || nav === "premium" || nav === "settings") {
      moreBtn.setAttribute("aria-current", "page");
    }
    var moreMenu = el("div", "z-more-menu hidden");
    moreMenu.id = "shellMoreMenu";
    moreMenu.innerHTML =
      '<a href="groups.html">Groups</a>' +
      '<a href="webinars.html">Webinars</a>' +
      '<a href="premium.html">Premium</a>' +
      '<a href="profile.html">Profile</a>' +
      '<a href="settings.html">Settings</a>';
    moreWrap.appendChild(moreBtn);
    moreWrap.appendChild(moreMenu);
    navBar.appendChild(moreWrap);
    root.appendChild(navBar);

    var account = el("button", "z-account-chip");
    account.type = "button";
    account.id = "accountToggle";
    account.innerHTML =
      '<div id="mePhoto" class="size-9 shrink-0"></div>' +
      '<span class="z-account-meta">' +
      '<span id="greeting" class="block truncate text-[13px] font-bold leading-4">Account</span>' +
      '<span id="handle" class="block truncate text-[12px] leading-4 text-x-muted"></span>' +
      "</span>";
    root.appendChild(account);

    var pop = el("div", "menu-pop absolute right-3 top-[3.6rem] z-50 hidden w-[220px] overflow-hidden rounded-2xl py-2");
    pop.id = "accountPopover";
    pop.innerHTML =
      '<a href="profile.html" class="block px-4 py-3 text-[15px] font-bold hover:bg-x-hover">View profile</a>' +
      '<a href="settings.html" class="block px-4 py-3 text-[15px] font-bold hover:bg-x-hover">Settings</a>' +
      '<a href="premium.html" class="block px-4 py-3 text-[15px] font-bold hover:bg-x-hover">Premium</a>' +
      '<button id="logout" type="button" class="w-full px-4 py-3 text-left text-[15px] font-bold hover:bg-x-hover">Log out</button>';
    root.appendChild(pop);

    moreBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = moreMenu.classList.toggle("hidden") === false;
      moreBtn.setAttribute("aria-expanded", open ? "true" : "false");
      pop.classList.add("hidden");
    });
  }

  function fillLeft(root) {
    root.innerHTML =
      '<section class="z-profile-card" aria-label="Your profile">' +
      '<div class="z-profile-cover" id="shellCover"></div>' +
      '<div class="z-profile-body">' +
      '<div class="z-profile-avatar" id="shellAvatar"></div>' +
      '<p id="shellName" class="text-[15px] font-extrabold leading-5">—</p>' +
      '<p id="shellHandle" class="text-[13px] text-x-muted"></p>' +
      '<p id="shellBio" class="mt-2 text-[13px] leading-4 text-x-muted"></p>' +
      '<div class="z-profile-stats">' +
      '<span><strong id="shellFollowing">0</strong> Following</span>' +
      '<span><strong id="shellFollowers">0</strong> Followers</span>' +
      "</div>" +
      '<a href="profile.html" class="x-btn-blue mt-3 h-9 w-full text-[14px]">My Profile</a>' +
      "</div></section>" +
      '<section class="z-card mt-3" aria-labelledby="people-heading">' +
      '<h2 id="people-heading" class="px-4 pt-3 pb-1 text-base font-extrabold">Who to follow</h2>' +
      '<div id="people"></div>' +
      "</section>" +
      '<p class="px-2 py-4 text-[12px] leading-4 text-x-muted">© 2026 Zivo</p>';
  }

  function fillRight(root) {
    root.innerHTML =
      '<section id="premiumPromoCard" class="z-card px-4 py-4">' +
      '<h2 class="text-lg font-extrabold">Get Premium</h2>' +
      '<p class="mt-1 text-[14px] leading-5 text-x-muted">A blue star on your profile and posts.</p>' +
      '<a href="premium.html" class="x-btn-blue mt-3 h-9 w-full text-[14px]">Subscribe</a>' +
      "</section>" +
      '<section class="z-card mt-3" aria-labelledby="trends-heading">' +
      '<h2 id="trends-heading" class="px-4 pt-3 pb-1 text-base font-extrabold">Trend for you</h2>' +
      '<div id="trends" class="px-4 pb-3"></div>' +
      "</section>";
  }

  function fillBottom(root, nav) {
    var items = [
      ["home", "feed.html", "Home", ICONS.home],
      ["groups", "groups.html", "Groups", ICONS.groups],
      ["chats", "chats.html", "Chats", ICONS.chats],
      ["webinars", "webinars.html", "Webinars", ICONS.webinars],
      ["blogs", "blogs.html", "Blogs", ICONS.blogs],
      ["notifications", "notifications.html", "Notifications", ICONS.notes],
      ["profile", "profile.html", "Profile", ICONS.profile],
      ["premium", "premium.html", "Premium", ICONS.premium],
    ];
    root.innerHTML = "";
    items.forEach(function (item) {
      var a = document.createElement("a");
      a.href = item[1];
      a.setAttribute("aria-label", item[2]);
      if (item[0] === "notifications") a.dataset.nav = "notifications";
      if (item[0] === nav) a.setAttribute("aria-current", "page");
      a.innerHTML = item[3];
      root.appendChild(a);
    });
  }

  function paintProfile(me) {
    var cover = document.getElementById("shellCover");
    var avatar = document.getElementById("shellAvatar");
    var nameEl = document.getElementById("shellName");
    var handleEl = document.getElementById("shellHandle");
    var bioEl = document.getElementById("shellBio");
    var followingEl = document.getElementById("shellFollowing");
    var followersEl = document.getElementById("shellFollowers");
    var mePhoto = document.getElementById("mePhoto");
    var greeting = document.getElementById("greeting");
    var handle = document.getElementById("handle");

    if (cover) {
      cover.innerHTML = "";
      if (me.cover) {
        var img = document.createElement("img");
        img.src = API + me.cover;
        img.alt = "";
        cover.appendChild(img);
      }
    }
    if (avatar) {
      avatar.innerHTML = "";
      avatar.appendChild(picture(me.photo, (me.name || "?").charAt(0), "size-14"));
    }
    if (nameEl) {
      nameEl.textContent = me.name || "Account";
      if (me.premium && typeof premiumMark === "function") {
        nameEl.appendChild(premiumMark());
      }
    }
    if (handleEl) handleEl.textContent = me.username ? "@" + me.username : "";
    if (bioEl) {
      if (me.bio) {
        bioEl.textContent = me.bio;
        bioEl.classList.remove("hidden");
      } else {
        bioEl.textContent = "";
        bioEl.classList.add("hidden");
      }
    }
    if (followingEl) followingEl.textContent = String(me.following_count || 0);
    if (followersEl) followersEl.textContent = String(me.followers_count || 0);

    if (mePhoto) {
      mePhoto.innerHTML = "";
      mePhoto.appendChild(picture(me.photo, (me.name || "?").charAt(0), "size-9"));
    }
    if (greeting) {
      greeting.textContent = me.name || "Account";
      if (me.premium && typeof premiumMark === "function") {
        greeting.appendChild(premiumMark());
      }
    }
    if (handle) handle.textContent = me.username ? "@" + me.username : "";

    var promo = document.getElementById("premiumPromoCard");
    if (promo && me.premium) {
      promo.innerHTML =
        '<div class="flex items-center gap-1.5"><span class="text-x-blue">★</span><h2 class="text-base font-extrabold">Premium Active</h2></div>' +
        '<p class="mt-1 text-[13px] leading-4 text-x-muted">Your blue star is active across your profile and posts.</p>';
    }

    var composerPhoto = document.getElementById("composerPhoto");
    if (composerPhoto && !composerPhoto.childNodes.length) {
      composerPhoto.appendChild(picture(me.photo, (me.name || "?").charAt(0), "size-10"));
    }
  }

  function renderPeopleList(box, people, opts) {
    opts = opts || {};
    var query = (opts.query || "").toLowerCase();
    var showAll = !!opts.showAll;
    var onFollow = opts.onFollow;
    var filtered = (people || []).filter(function (person) {
      if (!query) return true;
      return [person.name, person.username, person.bio].some(function (part) {
        return (part || "").toLowerCase().indexOf(query) !== -1;
      });
    });
    box.innerHTML = "";
    if (!filtered.length) {
      var empty = el("p", "px-4 py-4 text-[14px] text-x-muted");
      empty.textContent = query ? "No people match that search." : "No one else has joined yet.";
      box.appendChild(empty);
      return;
    }
    var list = showAll || query ? filtered : filtered.slice(0, 4);
    list.forEach(function (person) {
      var row = el("div", "flex items-center gap-2 px-3 py-2 hover:bg-x-hover");
      var link = el("a", "flex min-w-0 flex-1 items-center gap-3");
      link.href = profileHref(person.username, person.email);
      link.appendChild(picture(person.photo, (person.name || "?").charAt(0), "size-10"));
      var copy = el("div", "min-w-0 flex-1");
      var name = el("p", "text-[14px] leading-5 font-bold break-words");
      name.textContent = person.name;
      if (person.premium && typeof premiumMark === "function") {
        var nameRow = el("span", "flex min-w-0 items-center gap-1");
        nameRow.appendChild(name);
        nameRow.appendChild(premiumMark());
        copy.appendChild(nameRow);
      } else {
        copy.appendChild(name);
      }
      var meta = el("p", "text-[13px] leading-4 break-words text-x-muted");
      meta.textContent = person.username ? "@" + person.username : person.bio || "";
      copy.appendChild(meta);
      link.appendChild(copy);

      var button = document.createElement("button");
      button.type = "button";
      if (person.following) {
        button.className = "btn-following";
        button.innerHTML =
          '<span class="label-follow">Following</span><span class="label-unfollow">Unfollow</span>';
      } else {
        button.className = "btn-follow";
        button.textContent = "Follow";
      }
      button.addEventListener("click", function () {
        if (typeof onFollow === "function") onFollow(person);
      });
      row.appendChild(link);
      row.appendChild(button);
      box.appendChild(row);
    });
    if (!query && !showAll && filtered.length > 4) {
      var more = el("button", "w-full rounded-b-[1.35rem] px-4 py-3 text-left text-[14px] text-x-blue hover:bg-x-hover");
      more.type = "button";
      more.textContent = "Show more";
      more.addEventListener("click", function () {
        opts.showAll = true;
        renderPeopleList(box, people, opts);
      });
      box.appendChild(more);
    }
  }

  function extractTrends(posts) {
    var counts = {};
    (posts || []).slice(0, 80).forEach(function (post) {
      var text = post && post.text ? String(post.text) : "";
      var tags = text.match(/#[\w]+/g) || [];
      tags.forEach(function (tag) {
        var key = tag.toLowerCase();
        counts[key] = (counts[key] || 0) + 3;
      });
      text
        .toLowerCase()
        .replace(/[^a-z0-9#\s]/g, " ")
        .split(/\s+/)
        .forEach(function (word) {
          if (!word || word.length < 4 || STOP[word] || word.charAt(0) === "#") return;
          counts[word] = (counts[word] || 0) + 1;
        });
    });
    return Object.keys(counts)
      .map(function (key) {
        return { label: key.charAt(0) === "#" ? key : key, score: counts[key] };
      })
      .filter(function (item) {
        return item.score >= 2;
      })
      .sort(function (a, b) {
        return b.score - a.score;
      })
      .slice(0, 6);
  }

  function paintTrends(posts) {
    var box = document.getElementById("trends");
    if (!box) return;
    var trends = extractTrends(posts);
    box.innerHTML = "";
    if (!trends.length) {
      var empty = el("p", "py-3 text-[14px] text-x-muted");
      empty.textContent = "Trends will appear as people post.";
      box.appendChild(empty);
      return;
    }
    trends.forEach(function (trend, index) {
      var row = el("button", "block w-full rounded-xl px-0 py-2.5 text-left hover:bg-x-hover");
      row.type = "button";
      row.innerHTML =
        '<p class="text-[12px] text-x-muted">Trending · ' +
        (index + 1) +
        "</p>" +
        '<p class="text-[15px] font-extrabold leading-5">' +
        trend.label +
        "</p>" +
        '<p class="text-[12px] text-x-muted">' +
        trend.score +
        (trend.score === 1 ? " mention" : " mentions") +
        "</p>";
      row.addEventListener("click", function () {
        var search = document.getElementById("shellSearch") || document.getElementById("peopleSearch");
        if (search) {
          search.value = trend.label;
          search.dispatchEvent(new Event("input", { bubbles: true }));
          search.focus();
        }
      });
      box.appendChild(row);
    });
  }

  function wireAccountMenus() {
    document.addEventListener("click", function (e) {
      var pop = document.getElementById("accountPopover");
      var toggle = document.getElementById("accountToggle");
      var moreMenu = document.getElementById("shellMoreMenu");
      var moreBtn = document.getElementById("shellMoreToggle");
      if (toggle && toggle.contains(e.target)) {
        if (pop) pop.classList.toggle("hidden");
        if (moreMenu) moreMenu.classList.add("hidden");
        return;
      }
      if (pop && !pop.contains(e.target)) pop.classList.add("hidden");
      if (moreMenu && moreBtn && !moreWrapContains(moreBtn, moreMenu, e.target)) {
        moreMenu.classList.add("hidden");
        moreBtn.setAttribute("aria-expanded", "false");
      }
    });

    var logout = document.getElementById("logout");
    if (logout) {
      logout.addEventListener("click", function () {
        if (typeof signOut === "function") signOut();
      });
    }
  }

  function moreWrapContains(btn, menu, target) {
    return btn.contains(target) || menu.contains(target);
  }

  window.shellPicture = picture;
  window.shellProfileHref = profileHref;
  window.shellRenderPeople = renderPeopleList;
  window.shellPaintTrends = paintTrends;
  window.shellExtractTrends = extractTrends;

  window.initShell = function (options) {
    options = options || {};
    var body = document.body;
    if (!body.classList.contains("z-shell")) body.classList.add("z-shell");
    var nav = options.nav || body.getAttribute("data-nav") || "home";
    body.setAttribute("data-nav", nav);
    if (options.rails === false || options.rails === "off") {
      body.setAttribute("data-rails", "off");
    }

    var theme = document.querySelector('meta[name="theme-color"]');
    if (theme) theme.setAttribute("content", "#0f1419");

    var top = document.getElementById("zTopbar");
    if (top) fillTopbar(top, nav);
    var left = document.getElementById("zLeft");
    if (left && body.getAttribute("data-rails") !== "off") fillLeft(left);
    var right = document.getElementById("zRight");
    if (right && body.getAttribute("data-rails") !== "off") fillRight(right);
    var bottom = document.getElementById("zBottom");
    if (bottom) fillBottom(bottom, nav);

    wireAccountMenus();
    if (typeof options.onLogout === "function") {
      var logoutBtn = document.getElementById("logout");
      if (logoutBtn) {
        logoutBtn.addEventListener(
          "click",
          function (event) {
            event.stopImmediatePropagation();
            options.onLogout();
          },
          true
        );
      }
    }
    if (typeof refreshNotifyBadge === "function") refreshNotifyBadge();

    function loadPeopleRail() {
      var box = document.getElementById("people");
      if (!box) return Promise.resolve([]);
      return apiFetch("/users").then(function (result) {
        if (!result.ok) return [];
        var people = Array.isArray(result.data) ? result.data : [];
        renderPeopleList(box, people, {
          onFollow: function (person) {
            var path = person.following ? "/unfollow" : "/follow";
            apiFetch(path, {
              method: "POST",
              body: JSON.stringify({ user: person.email }),
            }).then(function (followResult) {
              if (followResult.ok) loadPeopleRail();
            });
          },
        });
        return people;
      });
    }

    function loadTrendsRail() {
      if (!document.getElementById("trends")) return Promise.resolve([]);
      return apiFetch("/posts").then(function (result) {
        if (!result.ok) return [];
        var posts = Array.isArray(result.data) ? result.data : [];
        paintTrends(posts);
        return posts;
      });
    }

    if (
      options.autoRails !== false &&
      body.getAttribute("data-rails") !== "off" &&
      typeof getToken === "function" &&
      getToken()
    ) {
      loadPeopleRail();
      loadTrendsRail();
    }

    return {
      picture: picture,
      profileHref: profileHref,
      renderPeople: renderPeopleList,
      paintTrends: paintTrends,
      paintProfile: paintProfile,
      loadPeople: loadPeopleRail,
      loadTrends: loadTrendsRail,
      loadMe: function (opts) {
        opts = opts || {};
        return apiFetch("/me").then(function (result) {
          if (!result.ok) return null;
          paintProfile(result.data);
          if (!opts.skipRails && body.getAttribute("data-rails") !== "off") {
            loadPeopleRail();
            loadTrendsRail();
          }
          return result.data;
        });
      },
    };
  };
})();
