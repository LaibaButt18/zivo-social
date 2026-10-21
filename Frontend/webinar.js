var REACTIONS = [
  { id: "heart", glyph: "\u2764\ufe0f" },
  { id: "haha", glyph: "\ud83d\ude02" },
  { id: "wow", glyph: "\ud83d\ude2e" },
  { id: "sad", glyph: "\ud83d\ude22" },
  { id: "like", glyph: "\ud83d\udc4d" },
];

var webinarId = 0;
var me = null;
var webinar = null;
var iceServers = [{ urls: "stun:stun.l.google.com:19302" }];
var socket = null;
var roomState = null;
var people = [];
var localStream = null;
var cameraTrack = null;
var micTrack = null;
var screenStream = null;
var usingScreen = false;
var pcs = {};
var remoteStreams = {};
var askingMedia = false;
var joined = false;
var gotRemote = false;
var failed = false;
var pollTimer = 0;
var triedAuto = false;
var historyLoaded = false;
var seenMessage = {};
var inviteMounted = false;
var previewAsked = false;

function reactionGlyph(id) {
  for (var i = 0; i < REACTIONS.length; i++) {
    if (REACTIONS[i].id === id) return REACTIONS[i].glyph;
  }
  return "";
}

function paramsId() {
  var value = new URLSearchParams(window.location.search).get("id");
  var id = parseInt(value, 10);
  if (!value || isNaN(id)) return 0;
  return id;
}

function whenText(unix) {
  if (!unix) return "No set time";
  var date = new Date(unix * 1000);
  if (isNaN(date.getTime())) return "No set time";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function statusLabel(status) {
  if (status === "live") return "Live";
  if (status === "ended") return "Ended";
  return "Upcoming";
}

function picture(src, letter, sizeClass, round) {
  var shape = round === false ? "rounded-2xl" : "rounded-full";
  var letterSize = sizeClass.indexOf("text-") === -1 ? "text-sm " : "";
  if (src) {
    var img = document.createElement("img");
    img.src = API + src;
    img.alt = "";
    img.className = "shrink-0 object-cover " + shape + " " + sizeClass;
    return img;
  }
  var fallback = document.createElement("span");
  fallback.className = "flex shrink-0 items-center justify-center bg-x-blue font-bold text-white " + letterSize + shape + " " + sizeClass;
  fallback.textContent = (letter || "?").charAt(0).toUpperCase();
  return fallback;
}

function setNotice(id, text) {
  var node = document.getElementById(id);
  if (!node) return;
  if (!text) {
    node.classList.add("hidden");
    node.textContent = "";
    return;
  }
  node.classList.remove("hidden");
  node.textContent = text;
}

function roleNow() {
  return roomState && roomState.you ? roomState.you : "";
}

function selfPerson() {
  for (var i = 0; i < people.length; i++) {
    if (people[i].email === me.email) return people[i];
  }
  return null;
}

function showBlock(id, on) {
  var node = document.getElementById(id);
  if (!node) return;
  var shown = node.getAttribute("data-show");
  if (shown) {
    node.className = on ? shown : "hidden";
    return;
  }
  node.classList.toggle("hidden", !on);
}

function showStage(mode, text) {
  var banner = document.getElementById("stageBanner");
  var label = document.getElementById("stageText");
  var retry = document.getElementById("retryStage");
  if (!banner) return;
  if (mode === "live") {
    failed = false;
    banner.className = "hidden";
    label.textContent = "";
    return;
  }
  banner.className = "absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black/70 px-6 text-center";
  label.textContent = text || "";
  retry.className = mode === "failed"
    ? "rounded-full bg-white px-4 py-2 text-[15px] font-bold text-x-ink"
    : "hidden";
}

function stopScreen() {
  if (screenStream) {
    screenStream.getTracks().forEach(function (track) {
      track.onended = null;
      track.stop();
    });
  }
  screenStream = null;
  usingScreen = false;
  replaceKind("video", cameraTrack || null);
  paintLocal();
  emitMedia();
}

function stopLocal() {
  stopScreen();
  if (localStream) {
    localStream.getTracks().forEach(function (track) { track.stop(); });
  }
  localStream = null;
  cameraTrack = null;
  micTrack = null;
  askingMedia = false;
  paintLocal();
}

function ensureLocal(wantVideo) {
  if (localStream) return Promise.resolve(localStream);
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return Promise.reject(new Error("This browser cannot use the camera or microphone."));
  }
  var constraints = {
    audio: true,
    video: wantVideo ? { width: { ideal: 1280 }, height: { ideal: 720 } } : false,
  };
  return navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
    rememberStream(stream);
    return stream;
  }).catch(function () {
    if (!wantVideo) {
      return Promise.reject(new Error("Allow the microphone to present."));
    }
    return navigator.mediaDevices.getUserMedia({ audio: true, video: false }).then(function (stream) {
      rememberStream(stream);
      return stream;
    }).catch(function () {
      return Promise.reject(new Error("Allow the camera or microphone to present."));
    });
  });
}

function rememberStream(stream) {
  localStream = stream;
  micTrack = stream.getAudioTracks()[0] || null;
  cameraTrack = stream.getVideoTracks()[0] || null;
  paintLocal();
}

function displayStream() {
  if (usingScreen && screenStream) return screenStream;
  return localStream;
}

function paintLocal() {
  var preview = document.getElementById("previewVideo");
  var stream = displayStream();
  if (preview && webinar && webinar.is_host && !joined) {
    if (stream) {
      preview.srcObject = stream;
      preview.classList.remove("hidden");
      preview.style.transform = usingScreen ? "" : "scaleX(-1)";
    }
  }
  var mineTile = document.getElementById(tileId(me ? me.email : ""));
  if (mineTile) {
    var video = mineTile.querySelector("video");
    if (video && stream && video.srcObject !== stream) video.srcObject = stream;
  }
}

function tileId(email) {
  return "tile-" + String(email || "").replace(/[^a-z0-9]/gi, "-");
}

function mediaState() {
  return {
    audio: !!(micTrack && micTrack.enabled),
    video: usingScreen ? true : !!(cameraTrack && cameraTrack.enabled),
    screen: usingScreen,
  };
}

function emitMedia() {
  if (!socket || !joined) return;
  socket.emit("media", mediaState());
  paintControls();
  paintPeople();
}

function closePc(email) {
  var entry = pcs[email];
  if (!entry) return;
  try { entry.pc.close(); } catch (err) { /* already closed */ }
  delete pcs[email];
  delete remoteStreams[email];
}

function closeAllPcs() {
  Object.keys(pcs).forEach(closePc);
}

function shouldOffer(person) {
  return !!(me && person && me.email < person.email);
}

function ensureSenders(pc) {
  if (!localStream) return;
  localStream.getTracks().forEach(function (track) {
    var sender = pc.getSenders().find(function (item) {
      return item.track && item.track.kind === track.kind;
    });
    if (!sender) pc.addTrack(track, localStream);
  });
}

function needsOffer(entry) {
  if (!entry || entry.makingOffer) return false;
  if (entry.pc.signalingState !== "stable") return false;
  if (entry.forceOffer) return true;
  if (!entry.pc.currentLocalDescription) return true;
  if (!localStream) return false;
  var senders = entry.pc.getSenders();
  var missing = false;
  localStream.getTracks().forEach(function (track) {
    var hasKind = senders.some(function (sender) {
      return sender.track && sender.track.kind === track.kind;
    });
    if (!hasKind) missing = true;
  });
  return missing;
}

function ensurePc(email) {
  if (pcs[email]) return pcs[email];
  var pc = new RTCPeerConnection({ iceServers: iceServers });
  var entry = { pc: pc, makingOffer: false, pendingIce: [] };
  pcs[email] = entry;
  ensureSenders(pc);
  pc.onicecandidate = function (event) {
    if (!event.candidate || !socket) return;
    socket.emit("signal", { to: email, kind: "ice", payload: event.candidate });
  };
  pc.ontrack = function (event) {
    var stream = event.streams && event.streams[0] ? event.streams[0] : new MediaStream([event.track]);
    remoteStreams[email] = stream;
    gotRemote = true;
    failed = false;
    showStage("live", "");
    paintStage();
  };
  pc.onconnectionstatechange = function () {
    if (pc.connectionState === "failed") {
      failed = true;
      showStage("failed", "Couldn't connect. Try again.");
    }
  };
  return entry;
}

function flushIce(entry) {
  var queued = entry.pendingIce || [];
  entry.pendingIce = [];
  queued.forEach(function (candidate) {
    entry.pc.addIceCandidate(candidate).catch(function () {});
  });
}

function offerTo(email) {
  var entry = ensurePc(email);
  if (!needsOffer(entry)) return;
  entry.forceOffer = false;
  ensureSenders(entry.pc);
  entry.makingOffer = true;
  entry.pc.createOffer().then(function (offer) {
    return entry.pc.setLocalDescription(offer);
  }).then(function () {
    if (socket) {
      socket.emit("signal", { to: email, kind: "offer", payload: entry.pc.localDescription });
    }
  }).catch(function () {
    failed = true;
    showStage("failed", "Couldn't connect. Try again.");
  }).then(function () {
    entry.makingOffer = false;
  });
}

function syncOffers() {
  if (!socket || !roomState || roomState.you_pending || !me) return;
  people.forEach(function (person) {
    if (!shouldOffer(person)) return;
    offerTo(person.email);
  });
}

function replaceKind(kind, track) {
  var added = false;
  Object.keys(pcs).forEach(function (email) {
    var entry = pcs[email];
    var sender = entry.pc.getSenders().find(function (item) {
      return item.track && item.track.kind === kind;
    });
    if (sender) {
      sender.replaceTrack(track || null);
      return;
    }
    if (!track) return;
    var stream = (kind === "video" && screenStream) || localStream || new MediaStream([track]);
    entry.pc.addTrack(track, stream);
    entry.forceOffer = true;
    added = true;
  });
  if (added) syncOffers();
}

function onSignal(message) {
  if (!message || !message.from || message.from === me.email) return;
  var entry = ensurePc(message.from);
  var pc = entry.pc;
  if (message.kind === "offer") {
    var collision = entry.makingOffer || pc.signalingState !== "stable";
    var polite = me.email > message.from;
    if (collision && !polite) return;
    var prepare = collision
      ? Promise.all([
        pc.setLocalDescription({ type: "rollback" }),
        pc.setRemoteDescription(message.payload),
      ])
      : pc.setRemoteDescription(message.payload);
    prepare.then(function () {
      ensureSenders(pc);
      return pc.createAnswer();
    }).then(function (answer) {
      return pc.setLocalDescription(answer);
    }).then(function () {
      flushIce(entry);
      if (socket) {
        socket.emit("signal", { to: message.from, kind: "answer", payload: pc.localDescription });
      }
    }).catch(function () {
      failed = true;
      showStage("failed", "Couldn't connect. Try again.");
    });
    return;
  }
  if (message.kind === "answer") {
    if (pc.signalingState !== "have-local-offer") return;
    pc.setRemoteDescription(message.payload).then(function () {
      flushIce(entry);
    }).catch(function () {});
    return;
  }
  if (message.kind === "ice" && message.payload) {
    if (!pc.remoteDescription) {
      entry.pendingIce.push(message.payload);
      return;
    }
    pc.addIceCandidate(message.payload).catch(function () {});
  }
}

function requestSpeakerMedia() {
  if (localStream) {
    if (socket) socket.emit("publish-ready", { webinar_id: webinarId });
    return;
  }
  if (askingMedia) return;
  askingMedia = true;
  ensureLocal(false).then(function () {
    askingMedia = false;
    if (socket) socket.emit("publish-ready", { webinar_id: webinarId });
    emitMedia();
  }).catch(function () {
    askingMedia = false;
    if (socket) socket.emit("publish-failed", { webinar_id: webinarId });
    setNotice("chatNotice", "Allow the microphone to speak.");
  });
}

function prunePcs() {
  var present = {};
  people.forEach(function (person) { present[person.email] = true; });
  Object.keys(pcs).forEach(function (email) {
    if (!present[email]) closePc(email);
  });
}

function tileStream(person) {
  if (person.email === me.email) return displayStream();
  return remoteStreams[person.email] || null;
}

function tileShowsVideo(person, stream) {
  if (person.email === me.email) {
    if (usingScreen && screenStream) return true;
    return !!(cameraTrack && cameraTrack.enabled);
  }
  if (!stream || (!person.video && !person.screen)) return false;
  return stream.getVideoTracks().some(function (track) { return track.readyState !== "ended"; });
}

function updateTileFace(tile, person) {
  tile.className = "relative h-full min-h-0 overflow-hidden rounded-2xl bg-[#15202b]";
  var video = tile.querySelector("video");
  var stream = tileStream(person);
  var showVideo = tileShowsVideo(person, stream);
  if (video && stream && video.srcObject !== stream) video.srcObject = stream;
  if (video) {
    video.style.transform = person.email === me.email && !usingScreen ? "scaleX(-1)" : "";
    video.classList.toggle("hidden", !showVideo);
  }
  var avatar = tile.querySelector("[data-avatar]");
  if (avatar) {
    avatar.classList.toggle("hidden", showVideo);
    if (!showVideo && !avatar.firstChild) {
      avatar.appendChild(picture(person.photo, person.name, "size-24 text-3xl"));
    }
  }
  var name = tile.querySelector("[data-name]");
  var label = person.name || "Someone";
  if (person.email === me.email) label += " (You)";
  if (person.role === "host") label += " · Host";
  name.textContent = label;
  var flags = tile.querySelector("[data-flags]");
  var bits = [];
  if (person.email === me.email) {
    var mineState = mediaState();
    if (!mineState.audio) bits.push("Muted");
    if (mineState.screen) bits.push("Screen");
  } else {
    if (!person.audio) bits.push("Muted");
    if (person.screen) bits.push("Screen");
  }
  flags.textContent = bits.join(" · ");
  flags.classList.toggle("hidden", bits.length === 0);
}

function stageGridClass(count) {
  if (count <= 1) return "grid h-full min-h-0 grid-cols-1";
  if (count === 2) return "grid h-full min-h-0 grid-cols-1 gap-3 sm:grid-cols-2";
  if (count <= 4) return "grid h-full min-h-0 grid-cols-2 grid-rows-2 gap-3";
  return "grid h-full min-h-0 auto-rows-fr grid-cols-2 gap-3 lg:grid-cols-3";
}

function ensureTile(person) {
  var id = tileId(person.email);
  var tile = document.getElementById(id);
  if (!tile) {
    tile = document.createElement("div");
    tile.id = id;
    var video = document.createElement("video");
    video.autoplay = true;
    video.playsInline = true;
    video.muted = person.email === me.email;
    video.className = "h-full w-full object-cover";
    var avatar = document.createElement("div");
    avatar.setAttribute("data-avatar", "");
    avatar.className = "absolute inset-0 flex items-center justify-center bg-[#15202b]";
    var caption = document.createElement("p");
    caption.setAttribute("data-name", "");
    caption.className = "absolute bottom-3 left-3 max-w-[85%] truncate rounded-full bg-black/60 px-3 py-1 text-[13px] font-bold text-white";
    var flags = document.createElement("p");
    flags.setAttribute("data-flags", "");
    flags.className = "absolute top-3 left-3 rounded-full bg-black/60 px-3 py-1 text-[13px] font-bold text-white";
    tile.appendChild(video);
    tile.appendChild(avatar);
    tile.appendChild(caption);
    tile.appendChild(flags);
  }
  updateTileFace(tile, person);
  return tile;
}

function paintStage() {
  var grid = document.getElementById("stageGrid");
  if (!grid) return;
  grid.className = stageGridClass(people.length);
  var keep = {};
  people.forEach(function (person) {
    keep[person.email] = true;
    var tile = ensureTile(person);
    if (tile.parentNode !== grid) grid.appendChild(tile);
  });
  Array.prototype.slice.call(grid.children).forEach(function (child) {
    var stay = false;
    people.forEach(function (person) {
      if (tileId(person.email) === child.id) stay = true;
    });
    if (!stay) child.remove();
  });
  Object.keys(remoteStreams).forEach(function (email) {
    if (!keep[email]) delete remoteStreams[email];
  });
  var count = document.getElementById("countLabel");
  var total = roomState ? roomState.count : people.length;
  count.textContent = total === 1 ? "1 person" : total + " people";
  if (!roomState || roomState.host_online || roleNow() === "host") {
    if (!failed && (roleNow() === "host" || roleNow() === "speaker" || gotRemote || total < 2)) {
      showStage("live", "");
    }
  } else if (!failed) {
    showStage("connecting", "Host reconnecting…");
  }
}

function paintPeople() {
  var box = document.getElementById("peopleList");
  box.innerHTML = "";
  if (!people.length) {
    var empty = document.createElement("p");
    empty.className = "px-4 py-3 text-[15px] text-x-muted";
    empty.textContent = joined ? "Nobody else is here yet." : "People appear here after they join.";
    box.appendChild(empty);
    return;
  }
  people.forEach(function (person) {
    var row = document.createElement("div");
    row.className = "flex items-center gap-3 px-4 py-2";
    row.appendChild(picture(person.photo, person.name, "size-9"));
    var copy = document.createElement("div");
    copy.className = "min-w-0 flex-1";
    var name = document.createElement("p");
    name.className = "flex min-w-0 items-center gap-1 truncate text-[15px] font-bold";
    var label = document.createElement("span");
    label.className = "truncate";
    label.textContent = person.name || "Someone";
    name.appendChild(label);
    if (person.premium) name.appendChild(premiumMark());
    var meta = document.createElement("p");
    meta.className = "truncate text-[13px] text-x-muted";
    var roleText = person.role === "host" ? "Host" : (person.role === "speaker" ? "Speaker" : "In the room");
    if (person.pending) roleText = "Turning on microphone";
    if (person.hand) roleText += " · Hand raised";
    meta.textContent = roleText;
    copy.appendChild(name);
    copy.appendChild(meta);
    row.appendChild(copy);
    if (roleNow() === "host" && person.email !== me.email) {
      var actions = document.createElement("div");
      actions.className = "flex shrink-0 flex-col gap-1";
      if (person.role === "listener") actions.appendChild(smallButton("Allow", function () {
        socket.emit("admit", { user: person.email });
      }));
      if (person.role === "speaker" || person.pending) actions.appendChild(smallButton("Stop", function () {
        socket.emit("revoke", { user: person.email });
      }));
      actions.appendChild(smallButton("Make host", function () {
        if (!window.confirm("Make " + (person.name || "this person") + " the host? You will keep presenting.")) return;
        socket.emit("pass-host", { user: person.email });
      }));
      actions.appendChild(smallButton("Remove", function () {
        if (!window.confirm("Remove " + (person.name || "this person") + " from the room?")) return;
        socket.emit("kick", { user: person.email });
      }));
      row.appendChild(actions);
    }
    box.appendChild(row);
  });
}

function smallButton(text, onClick) {
  var button = document.createElement("button");
  button.type = "button";
  button.className = "rounded-full px-2 py-0.5 text-[13px] font-bold text-x-blue hover:bg-x-blue/10";
  button.textContent = text;
  button.addEventListener("click", onClick);
  return button;
}

function paintHands() {
  var box = document.getElementById("handsList");
  var hands = roomState && roomState.hands ? roomState.hands : [];
  box.innerHTML = "";
  if (!hands.length) {
    var empty = document.createElement("p");
    empty.className = "px-4 pb-3 text-[15px] text-x-muted";
    empty.textContent = "No raised hands.";
    box.appendChild(empty);
    return;
  }
  hands.forEach(function (email) {
    var person = null;
    people.forEach(function (item) { if (item.email === email) person = item; });
    if (!person) return;
    var row = document.createElement("div");
    row.className = "flex items-center gap-3 px-4 py-2";
    row.appendChild(picture(person.photo, person.name, "size-8 text-xs"));
    var name = document.createElement("p");
    name.className = "min-w-0 flex-1 truncate text-[15px] font-bold";
    name.textContent = person.name || "Someone";
    row.appendChild(name);
    if (roleNow() === "host") {
      row.appendChild(smallButton("Admit", function () {
        socket.emit("admit", { user: person.email });
      }));
      row.appendChild(smallButton("Dismiss", function () {
        socket.emit("lower-hand", { user: person.email });
      }));
    }
    box.appendChild(row);
  });
}

function setControlLabel(button, label) {
  button.setAttribute("aria-label", label);
  button.title = label;
}

function showControlIcon(button, on) {
  var liveIcon = button.querySelector("[data-on]");
  var offIcon = button.querySelector("[data-off]");
  if (liveIcon) liveIcon.classList.toggle("hidden", !on);
  if (offIcon) offIcon.classList.toggle("hidden", on);
}

function markControl(button, hot, tone) {
  button.classList.toggle("border-transparent", hot);
  button.classList.toggle("text-white", hot);
  button.classList.toggle("bg-x-danger", hot && tone !== "blue");
  button.classList.toggle("bg-x-blue", hot && tone === "blue");
}

function paintControls() {
  var presenter = roleNow() === "host" || roleNow() === "speaker";
  showBlock("micButton", joined);
  showBlock("cameraButton", joined);
  showBlock("shareButton", joined);
  showBlock("handButton", joined && !presenter);
  showBlock("endButton", roleNow() === "host");
  var state = mediaState();
  var mic = document.getElementById("micButton");
  var camera = document.getElementById("cameraButton");
  var share = document.getElementById("shareButton");
  var hand = document.getElementById("handButton");
  var end = document.getElementById("endButton");
  setControlLabel(mic, state.audio ? "Mute" : "Unmute");
  mic.setAttribute("aria-pressed", state.audio ? "true" : "false");
  showControlIcon(mic, state.audio);
  markControl(mic, !state.audio, "danger");
  var cameraOn = !!(state.video && !usingScreen);
  setControlLabel(camera, cameraOn ? "Camera off" : "Camera on");
  camera.setAttribute("aria-pressed", cameraOn ? "true" : "false");
  camera.disabled = usingScreen;
  showControlIcon(camera, cameraOn);
  markControl(camera, !cameraOn, "danger");
  setControlLabel(share, usingScreen ? "Stop sharing" : "Share screen");
  share.setAttribute("aria-pressed", usingScreen ? "true" : "false");
  showControlIcon(share, !usingScreen);
  markControl(share, usingScreen, "blue");
  if (end) setControlLabel(end, "End");
  var minePerson = selfPerson();
  var raised = !!(minePerson && minePerson.hand);
  if (roomState && roomState.you_pending) {
    setControlLabel(hand, "Allow the microphone");
    hand.disabled = true;
  } else {
    hand.disabled = false;
    setControlLabel(hand, raised ? "Lower hand" : "Raise hand");
  }
  hand.setAttribute("aria-pressed", raised ? "true" : "false");
  markControl(hand, raised, "blue");
  showBlock("inviteBox", roleNow() === "host");
}

function setChatReady(on) {
  var input = document.getElementById("chatText");
  var send = document.getElementById("chatSend");
  if (!input || !send) return;
  input.disabled = !on;
  send.disabled = !on;
  input.placeholder = on ? "Say something" : "Chat starts when the room is live";
}

function addMessage(message) {
  if (!message || seenMessage[message.id]) return;
  seenMessage[message.id] = true;
  var empty = document.getElementById("chatEmpty");
  if (empty) empty.remove();
  var box = document.getElementById("messages");
  var stick = box.scrollHeight - box.scrollTop - box.clientHeight < 48;
  var row = document.createElement("div");
  row.className = "px-4 py-2";
  var name = document.createElement("p");
  name.className = "truncate text-[13px] font-bold";
  name.textContent = message.email === me.email ? "You" : (message.name || "Someone");
  var text = document.createElement("p");
  text.className = "text-[15px] leading-5 break-words";
  text.textContent = message.text || "";
  var time = document.createElement("p");
  time.className = "text-[12px] text-x-muted";
  time.textContent = whenText(message.created_at);
  row.appendChild(name);
  row.appendChild(text);
  row.appendChild(time);
  box.appendChild(row);
  if (stick) box.scrollTop = box.scrollHeight;
}

function loadHistory() {
  return apiFetch("/webinars/" + webinarId + "/messages").then(function (result) {
    if (!result.ok) return;
    historyLoaded = true;
    var box = document.getElementById("messages");
    box.innerHTML = "";
    seenMessage = {};
    (result.data.messages || []).forEach(addMessage);
    if (!box.children.length) {
      var empty = document.createElement("p");
      empty.id = "chatEmpty";
      empty.className = "px-4 py-3 text-[15px] text-x-muted";
      empty.textContent = "No messages yet.";
      box.appendChild(empty);
    }
  });
}

function floatReaction(name, emoji) {
  var layer = document.getElementById("floaters");
  var item = document.createElement("p");
  item.className = "pointer-events-none absolute rounded-full bg-black/70 px-3 py-1 text-sm text-white";
  item.style.left = "16px";
  item.style.bottom = (24 + Math.floor(Math.random() * 72)) + "px";
  item.textContent = (name || "Someone") + " " + reactionGlyph(emoji);
  layer.appendChild(item);
  setTimeout(function () { item.remove(); }, 3000);
}

function bindSocket() {
  socket.on("room", function (data) {
    roomState = data;
    people = data.people || [];
    joined = true;
    clearTimeout(pollTimer);
    showBlock("lobby", false);
    showBlock("liveView", true);
    document.getElementById("roomTitle").textContent = webinar ? webinar.title : "Webinar";
    prunePcs();
    paintStage();
    paintPeople();
    paintHands();
    paintControls();
    if (data.you === "host") mountInvite();
    if (data.you_pending) requestSpeakerMedia();
    syncOffers();
    if (!historyLoaded) loadHistory();
    setChatReady(true);
  });
  socket.on("signal", onSignal);
  socket.on("media", function (data) {
    people.forEach(function (person) {
      if (person.email !== data.email) return;
      person.audio = !!data.audio;
      person.video = !!data.video;
      person.screen = !!data.screen;
    });
    paintStage();
    paintPeople();
    if (me && data.email && me.email < data.email) {
      var remote = remoteStreams[data.email];
      var hasVideo = remote && remote.getVideoTracks().some(function (track) {
        return track.readyState !== "ended";
      });
      if (!remote || (data.video && !hasVideo)) {
        var entry = pcs[data.email];
        if (entry) entry.forceOffer = true;
        offerTo(data.email);
      }
    }
  });
  socket.on("hands", function (data) {
    if (!roomState) roomState = {};
    roomState.hands = data.hands || [];
    paintHands();
    paintControls();
  });
  socket.on("admitted", function () {
    requestSpeakerMedia();
  });
  socket.on("revoked", function (data) {
    if (!data) return;
    if (data.email === me.email) {
      stopLocal();
      closeAllPcs();
      gotRemote = false;
      if (roomState) roomState.you = "listener";
    } else {
      closePc(data.email);
    }
  });
  socket.on("kicked", function (data) {
    joined = false;
    closeAllPcs();
    stopLocal();
    if (socket) socket.disconnect();
    showBlock("liveView", false);
    showBlock("lobby", true);
    setNotice("lobbyNotice", (data && data.message) || "The host removed you.");
    showBlock("goLive", false);
    showBlock("joinLive", false);
    showBlock("startAgain", false);
    setChatReady(false);
  });
  socket.on("ended", function () {
    joined = false;
    failed = false;
    closeAllPcs();
    stopLocal();
    if (webinar) {
      webinar.status = "ended";
      webinar.is_host = roleNow() === "host" || webinar.is_host;
    }
    showBlock("liveView", false);
    showBlock("lobby", true);
    paintLobby();
    setNotice("lobbyNotice", "This session ended.");
  });
  socket.on("chat", addMessage);
  socket.on("react", function (data) {
    if (!data) return;
    floatReaction(data.name, data.emoji);
  });
  socket.on("replaced", function (data) {
    joined = false;
    closeAllPcs();
    stopLocal();
    showBlock("liveView", false);
    showBlock("lobby", true);
    setNotice("lobbyNotice", (data && data.message) || "You joined in another window.");
    showBlock("joinLive", false);
    showBlock("goLive", false);
  });
  socket.on("publish-failed", function (data) {
    var name = data && data.name ? data.name : "That person";
    setNotice("chatNotice", name + " couldn't turn on the microphone.");
  });
  socket.on("notice", function (data) {
    setNotice("chatNotice", (data && data.message) || "Something went wrong.");
  });
}

function connectAndJoin() {
  if (typeof io !== "function") {
    return Promise.reject(new Error("Live connection could not start."));
  }
  if (socket && socket.connected) {
    socket.emit("join", { webinar_id: webinarId });
    return Promise.resolve();
  }
  if (socket) {
    socket.disconnect();
    socket = null;
  }
  return new Promise(function (resolve, reject) {
    var settled = false;
    socket = io(API, {
      auth: { token: localStorage.getItem("zivo_token") || "" },
      transports: ["websocket", "polling"],
    });
    bindSocket();
    socket.on("connect", function () {
      socket.emit("join", { webinar_id: webinarId });
      if (!settled) {
        settled = true;
        resolve();
      }
    });
    socket.on("connect_error", function () {
      showStage("failed", "Couldn't connect. Try again.");
      if (!settled) {
        settled = true;
        reject(new Error("Couldn't connect. Try again."));
      }
    });
  });
}

function enterLive() {
  showBlock("lobby", false);
  showBlock("liveView", true);
  showStage("connecting", "Connecting…");
  return ensureLocal(true).catch(function () { return null; }).then(function () {
    return connectAndJoin();
  }).then(function () {
    emitMedia();
    syncOffers();
  });
}

function paintLobby() {
  if (!webinar) return;
  document.getElementById("lobbyTitle").textContent = webinar.title || "Webinar";
  document.getElementById("roomTitle").textContent = webinar.title || "Webinar";
  var host = webinar.host || {};
  document.getElementById("lobbyHost").textContent = host.name ? "Hosted by " + host.name : "";
  document.getElementById("lobbyWhen").textContent = statusLabel(webinar.status) + " · " + whenText(webinar.starts_at);
  document.getElementById("lobbyAbout").textContent = webinar.description || (webinar.is_host
    ? "Check the preview, then go live. Listeners can join once you start."
    : "Join to listen. The host can let you speak.");
  var cover = document.getElementById("lobbyCover");
  if (webinar.cover) {
    cover.src = API + webinar.cover;
    cover.classList.remove("hidden");
  } else {
    cover.classList.add("hidden");
    cover.removeAttribute("src");
  }
  var hostWaiting = webinar.is_host && webinar.status !== "ended";
  var canJoin = webinar.status === "live";
  var canRestart = webinar.is_host && webinar.status === "ended";
  showBlock("goLive", webinar.is_host && webinar.status !== "live" && webinar.status !== "ended");
  showBlock("previewWrap", hostWaiting && webinar.status !== "live");
  showBlock("joinLive", canJoin);
  showBlock("startAgain", canRestart);
  document.getElementById("joinLive").textContent = webinar.is_host ? "Rejoin" : "Join";
  if (webinar.status === "live" && !webinar.is_host) {
    var count = webinar.listener_count || 0;
    document.getElementById("lobbyWhen").textContent = "Live · " + (count === 1 ? "1 person here" : count + " people here");
  }
  paintPeople();
  paintHands();
  setChatReady(false);
  if (hostWaiting && webinar.status !== "live" && !previewAsked) {
    previewAsked = true;
    ensureLocal(true).then(function () {
      paintLocal();
    }).catch(function (err) {
      setNotice("lobbyNotice", err.message || "Allow the camera or microphone to present.");
    });
  }
  if (webinar.is_host && webinar.status === "live" && !joined && !triedAuto) {
    triedAuto = true;
    enterLive().catch(function (err) {
      joined = false;
      triedAuto = true;
      showBlock("liveView", false);
      showBlock("lobby", true);
      paintLobby();
      setNotice("lobbyNotice", err.message || "Couldn't connect. Try again.");
    });
  }
}

function refreshWebinar() {
  return apiFetch("/webinars/" + webinarId).then(function (result) {
    if (result.status === 401) {
      clearToken();
      window.location.href = "loginpage.html";
      return;
    }
    if (!result.ok) {
      setNotice("lobbyNotice", result.data.message || "That webinar was not found.");
      return;
    }
    webinar = result.data;
    if (!joined) paintLobby();
    if (!joined && webinar.status !== "ended") {
      clearTimeout(pollTimer);
      pollTimer = setTimeout(refreshWebinar, 3000);
    }
  });
}

function mountInvite() {
  if (inviteMounted) return;
  if (!(webinar && webinar.is_host) && roleNow() !== "host") return;
  inviteMounted = true;
  var box = document.getElementById("inviteBox");
  mountUserSearch(box, {
    placeholder: "Invite by name",
    inset: false,
    onSelect: function (person) {
      return apiFetch("/webinars/" + webinarId + "/invite", {
        method: "POST",
        body: JSON.stringify({ user: person.email }),
      });
    },
  });
}

function bindRoom() {
  document.getElementById("goLive").addEventListener("click", function () {
    setNotice("lobbyNotice", "");
    var button = document.getElementById("goLive");
    button.disabled = true;
    ensureLocal(true).then(function () {
      return apiFetch("/webinars/" + webinarId + "/start", { method: "POST", body: "{}" });
    }).then(function (result) {
      button.disabled = false;
      if (!result || !result.ok) {
        throw new Error((result && result.data && result.data.message) || "Could not start this webinar.");
      }
      webinar = result.data;
      return enterLive();
    }).catch(function (err) {
      button.disabled = false;
      joined = false;
      triedAuto = true;
      showBlock("liveView", false);
      showBlock("lobby", true);
      paintLobby();
      setNotice("lobbyNotice", err.message || "Could not start this webinar.");
    });
  });

  document.getElementById("startAgain").addEventListener("click", function () {
    document.getElementById("goLive").click();
  });

  document.getElementById("joinLive").addEventListener("click", function () {
    setNotice("lobbyNotice", "");
    enterLive().catch(function (err) {
      joined = false;
      triedAuto = true;
      showBlock("liveView", false);
      showBlock("lobby", true);
      paintLobby();
      setNotice("lobbyNotice", err.message || "Couldn't connect. Try again.");
    });
  });

  document.getElementById("retryStage").addEventListener("click", function () {
    failed = false;
    gotRemote = false;
    closeAllPcs();
    showStage("connecting", "Connecting…");
    people.forEach(function (person) {
      if (me && person.email !== me.email) offerTo(person.email);
    });
  });

  document.getElementById("micButton").addEventListener("click", function () {
    if (!micTrack) return;
    micTrack.enabled = !micTrack.enabled;
    emitMedia();
    paintStage();
  });

  document.getElementById("cameraButton").addEventListener("click", function () {
    if (usingScreen) return;
    if (!cameraTrack) {
      navigator.mediaDevices.getUserMedia({ video: true, audio: false }).then(function (stream) {
        cameraTrack = stream.getVideoTracks()[0] || null;
        if (cameraTrack && localStream) localStream.addTrack(cameraTrack);
        replaceKind("video", cameraTrack);
        syncOffers();
        paintLocal();
        emitMedia();
        paintStage();
      }).catch(function () {
        setNotice("chatNotice", "Allow the camera to turn video on.");
      });
      return;
    }
    cameraTrack.enabled = !cameraTrack.enabled;
    paintLocal();
    emitMedia();
    paintStage();
  });

  document.getElementById("shareButton").addEventListener("click", function () {
    if (usingScreen) {
      stopScreen();
      paintStage();
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      setNotice("chatNotice", "This browser cannot share the screen.");
      return;
    }
    navigator.mediaDevices.getDisplayMedia({ video: true, audio: false }).then(function (stream) {
      screenStream = stream;
      usingScreen = true;
      var track = stream.getVideoTracks()[0];
        if (track) {
          track.onended = function () {
            stopScreen();
            paintStage();
          };
          replaceKind("video", track);
        }
      paintLocal();
      emitMedia();
      paintStage();
    }).catch(function () {
      setNotice("chatNotice", "Screen sharing was cancelled.");
    });
  });

  document.getElementById("handButton").addEventListener("click", function () {
    if (!socket) return;
    var minePerson = selfPerson();
    if (minePerson && minePerson.hand) socket.emit("lower-hand", {});
    else socket.emit("raise-hand", {});
  });

  document.getElementById("leaveButton").addEventListener("click", function () {
    if (roleNow() === "host") {
      if (!window.confirm("Leaving ends the webinar for everyone.")) return;
      if (socket) socket.emit("end", {});
      return;
    }
    if (socket) socket.emit("leave", {});
    closeAllPcs();
    stopLocal();
    window.location.href = "webinars.html";
  });

  document.getElementById("endButton").addEventListener("click", function () {
    if (!window.confirm("End this webinar for everyone?")) return;
    if (socket) socket.emit("end", {});
  });

  document.getElementById("chatForm").addEventListener("submit", function (event) {
    event.preventDefault();
    var input = document.getElementById("chatText");
    var text = input.value.trim();
    if (!text) return;
    if (!socket || !joined) {
      setNotice("chatNotice", "Chat starts when the room is live.");
      return;
    }
    if (text.length > 1000) {
      setNotice("chatNotice", "Messages can be 1,000 characters at most.");
      return;
    }
    setNotice("chatNotice", "");
    socket.emit("chat", { text: text });
    input.value = "";
  });

  REACTIONS.forEach(function (item) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "rounded-full px-2 py-1 text-lg hover:bg-black/5";
    button.textContent = item.glyph;
    button.setAttribute("aria-label", item.id);
    button.addEventListener("click", function () {
      if (socket && joined) socket.emit("react", { emoji: item.id });
    });
    document.getElementById("reactionBar").appendChild(button);
  });
}

function bootRoom() {
  webinarId = paramsId();
  if (!localStorage.getItem("zivo_token")) {
    window.location.href = "loginpage.html";
    return;
  }
  if (!webinarId) {
    window.location.href = "webinars.html";
    return;
  }
  bindRoom();
  apiFetch("/me").then(function (result) {
    if (!result.ok) {
      clearToken();
      window.location.href = "loginpage.html";
      return;
    }
    me = result.data;
    document.getElementById("greeting").textContent = me.name;
    if (me.premium) document.getElementById("greeting").appendChild(premiumMark());
    document.getElementById("mePhoto").appendChild(picture(me.photo, me.name, "size-10"));
    if (me.username) document.getElementById("handle").textContent = "@" + me.username;
    return apiFetch("/webinars/ice");
  }).then(function (result) {
    if (result && result.ok && result.data.iceServers) iceServers = result.data.iceServers;
    return refreshWebinar();
  }).then(function () {
    mountInvite();
  }).catch(function () {
    setNotice("lobbyNotice", "Cannot reach the server.");
  });

  document.addEventListener("click", function (event) {
    var pop = document.getElementById("accountPopover");
    var toggle = document.getElementById("accountToggle");
    if (!pop || !toggle) return;
    if (toggle.contains(event.target)) {
      pop.classList.toggle("hidden");
      return;
    }
    if (!pop.contains(event.target)) pop.classList.add("hidden");
  });
  document.getElementById("logout").addEventListener("click", function () {
    if (roleNow() === "host" && joined && socket) socket.emit("end", {});
    else if (socket) socket.disconnect();
    apiFetch("/logout", { method: "POST", body: "{}" }).finally(function () {
      clearToken();
      window.location.href = "loginpage.html";
    });
  });
}

bootRoom();
