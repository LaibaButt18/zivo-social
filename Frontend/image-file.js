var IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
var IMAGE_MAX_BYTES = 12 * 1024 * 1024;
var POST_CROP_ASPECTS = [
  { id: "original", label: "Original" },
  { id: "wide", label: "Wide", ratio: 16 / 9 },
  { id: "square", label: "Square", ratio: 1 },
  { id: "portrait", label: "Portrait", ratio: 4 / 5 },
];

function imageKind(file) {
  if (!file) return "";
  if (IMAGE_TYPES.indexOf(file.type) !== -1) return file.type;
  var name = String(file.name || "").toLowerCase();
  if (/\.jpe?g$/.test(name)) return "image/jpeg";
  if (/\.png$/.test(name)) return "image/png";
  if (/\.gif$/.test(name)) return "image/gif";
  if (/\.webp$/.test(name)) return "image/webp";
  return "";
}

function imageFileProblem(file) {
  if (!file) return "";
  if (!imageKind(file) || file.size === 0 || file.size > IMAGE_MAX_BYTES) {
    return "Use a jpg, png, gif, or webp under 12 MB.";
  }
  return "";
}

function resizeImageFile(file, edge) {
  return new Promise(function (resolve) {
    var kind = imageKind(file);
    if (!file || kind === "" || kind === "image/gif") {
      resolve(file);
      return;
    }
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var sourceWidth = img.naturalWidth || img.width;
      var sourceHeight = img.naturalHeight || img.height;
      var longest = Math.max(sourceWidth, sourceHeight);
      var scale = longest > edge ? edge / longest : 1;
      var width = Math.max(1, Math.round(sourceWidth * scale));
      var height = Math.max(1, Math.round(sourceHeight * scale));
      var canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d").drawImage(img, 0, 0, width, height);
      var type = kind === "image/png" ? "image/png" : kind === "image/webp" ? "image/webp" : "image/jpeg";
      function finish(blob) {
        URL.revokeObjectURL(url);
        if (!blob) {
          resolve(file);
          return;
        }
        var base = String(file.name || "photo").replace(/\.[^.]+$/, "") || "photo";
        var ext = type === "image/png" ? ".png" : type === "image/webp" ? ".webp" : ".jpg";
        resolve(new File([blob], base + ext, { type: type, lastModified: Date.now() }));
      }
      if (type === "image/png") canvas.toBlob(finish, type);
      else canvas.toBlob(finish, type, 0.82);
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      resolve(file);
    };
    img.src = url;
  });
}

function prepareImageFile(file, edge) {
  var problem = imageFileProblem(file);
  if (!file) return Promise.resolve({ problem: "", file: null });
  if (problem) return Promise.resolve({ problem: problem, file: null });
  return resizeImageFile(file, edge || 1600).then(function (next) {
    return { problem: "", file: next };
  });
}

function cropIconSvg() {
  return '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 3v12a3 3 0 0 0 3 3h12"/><path stroke-linecap="round" stroke-linejoin="round" d="M3 6h12a3 3 0 0 1 3 3v12"/></svg>';
}

function makeCropButton() {
  var button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", "Crop");
  button.innerHTML = cropIconSvg() + '<span>Crop</span>';
  button.style.cssText = "position:absolute;left:8px;bottom:8px;z-index:2;display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 12px;border:0;border-radius:999px;background:rgba(15,20,25,.82);color:#fff;font:700 13px/1 Inter,sans-serif;cursor:pointer;";
  return button;
}

function openImageCrop(file, options) {
  options = options || {};
  return new Promise(function (resolve) {
    var kind = imageKind(file);
    if (!file || kind === "" || kind === "image/gif") {
      resolve(null);
      return;
    }
    var url = URL.createObjectURL(file);
    var source = new Image();
    source.onload = function () { mount(source); };
    source.onerror = function () {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    source.src = url;

    function mount(image) {
      var nw = image.naturalWidth || image.width;
      var nh = image.naturalHeight || image.height;
      var aspects = options.circle ? [{ id: "square", label: "Square", ratio: 1 }] : (options.aspects || POST_CROP_ASPECTS);
      var aspectIndex = 0;
      var frameW = 320;
      var frameH = 320;
      var zoom = 1;
      var base = 1;
      var scale = 1;
      var offsetX = 0;
      var offsetY = 0;
      var previousOverflow = document.body.style.overflow;
      var settled = false;

      var overlay = document.createElement("div");
      overlay.style.cssText = "position:fixed;inset:0;z-index:80;display:flex;align-items:center;justify-content:center;padding:16px;background:rgba(0,0,0,.72);";
      var sheet = document.createElement("div");
      sheet.style.cssText = "width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:auto;box-sizing:border-box;border:1px solid var(--color-x-line);border-radius:16px;background:var(--color-x-panel);color:var(--color-x-ink);box-shadow:0 24px 80px rgba(0,0,0,.45);";
      var bar = document.createElement("div");
      bar.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-bottom:1px solid var(--color-x-line);";
      var cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Cancel";
      cancel.style.cssText = "height:36px;padding:0 12px;border:0;border-radius:999px;background:transparent;color:var(--color-x-ink);font:700 15px/1 Inter,sans-serif;cursor:pointer;";
      var title = document.createElement("p");
      title.textContent = options.title || "Crop";
      title.style.cssText = "margin:0;font:800 17px/1.2 Inter,sans-serif;";
      var apply = document.createElement("button");
      apply.type = "button";
      apply.textContent = "Apply";
      apply.style.cssText = "height:36px;padding:0 16px;border:0;border-radius:999px;background:#1d9bf0;color:#fff;font:700 15px/1 Inter,sans-serif;cursor:pointer;";
      bar.appendChild(cancel);
      bar.appendChild(title);
      bar.appendChild(apply);

      var aspectsRow = document.createElement("div");
      aspectsRow.style.cssText = "display:" + (options.circle || aspects.length < 2 ? "none" : "flex") + ";flex-wrap:wrap;gap:8px;padding:12px 14px 0;";
      var stage = document.createElement("div");
      stage.style.cssText = "display:flex;justify-content:center;padding:16px 14px 8px;";
      var viewport = document.createElement("div");
      viewport.style.cssText = "position:relative;overflow:hidden;background:#000;border-radius:" + (options.circle ? "999px" : "12px") + ";touch-action:none;cursor:grab;";
      var imgEl = document.createElement("img");
      imgEl.src = url;
      imgEl.alt = "";
      imgEl.draggable = false;
      imgEl.style.cssText = "position:absolute;left:0;top:0;max-width:none;user-select:none;pointer-events:none;transform-origin:0 0;";
      var grid = document.createElement("div");
      grid.style.cssText = "position:absolute;inset:0;pointer-events:none;background-image:linear-gradient(to right,rgba(255,255,255,.28) 1px,transparent 1px),linear-gradient(to bottom,rgba(255,255,255,.28) 1px,transparent 1px);background-size:33.33% 100%,100% 33.33%;background-position:33.33% 0,0 33.33%;";
      viewport.appendChild(imgEl);
      viewport.appendChild(grid);
      stage.appendChild(viewport);

      var controls = document.createElement("div");
      controls.style.cssText = "display:flex;align-items:center;gap:12px;padding:8px 16px 16px;";
      var zoomLabel = document.createElement("span");
      zoomLabel.textContent = "Zoom";
      zoomLabel.style.cssText = "font:600 13px/1 Inter,sans-serif;color:var(--color-x-muted);";
      var slider = document.createElement("input");
      slider.type = "range";
      slider.min = "1";
      slider.max = "3";
      slider.step = "0.01";
      slider.value = "1";
      slider.setAttribute("aria-label", "Zoom");
      slider.style.cssText = "flex:1;accent-color:#1d9bf0;";
      var hint = document.createElement("span");
      hint.textContent = "Drag to move";
      hint.style.cssText = "font:500 13px/1 Inter,sans-serif;color:var(--color-x-muted);";
      controls.appendChild(zoomLabel);
      controls.appendChild(slider);
      controls.appendChild(hint);

      sheet.appendChild(bar);
      sheet.appendChild(aspectsRow);
      sheet.appendChild(stage);
      sheet.appendChild(controls);
      overlay.appendChild(sheet);
      document.body.appendChild(overlay);
      document.body.style.overflow = "hidden";

      function ratioFor(choice) {
        if (options.circle) return 1;
        if (choice && choice.ratio) return choice.ratio;
        var raw = nw / nh;
        if (raw > 1.91) return 1.91;
        if (raw < 0.8) return 0.8;
        return raw;
      }

      function clamp() {
        scale = base * zoom;
        var minX = frameW - nw * scale;
        var minY = frameH - nh * scale;
        if (offsetX > 0) offsetX = 0;
        if (offsetY > 0) offsetY = 0;
        if (offsetX < minX) offsetX = minX;
        if (offsetY < minY) offsetY = minY;
      }

      function place() {
        imgEl.style.width = (nw * scale) + "px";
        imgEl.style.height = (nh * scale) + "px";
        imgEl.style.transform = "translate(" + offsetX + "px," + offsetY + "px)";
      }

      function center() {
        scale = base * zoom;
        offsetX = (frameW - nw * scale) / 2;
        offsetY = (frameH - nh * scale) / 2;
        clamp();
        place();
      }

      function layoutFrame(resetZoom) {
        var ratio = ratioFor(aspects[aspectIndex]);
        var viewW = overlay.clientWidth || window.innerWidth;
        var viewH = overlay.clientHeight || window.innerHeight;
        var maxW = Math.min(560, viewW - 64);
        var maxH = Math.min(420, viewH - 220);
        frameW = maxW;
        frameH = Math.round(frameW / ratio);
        if (frameH > maxH) {
          frameH = maxH;
          frameW = Math.round(frameH * ratio);
        }
        frameW = Math.max(180, frameW);
        frameH = Math.max(180, frameH);
        viewport.style.width = frameW + "px";
        viewport.style.height = frameH + "px";
        base = Math.max(frameW / nw, frameH / nh);
        if (resetZoom) {
          zoom = 1;
          slider.value = "1";
        }
        center();
        paintAspects();
      }

      function paintAspects() {
        aspectsRow.innerHTML = "";
        aspects.forEach(function (choice, index) {
          var button = document.createElement("button");
          button.type = "button";
          button.textContent = choice.label;
          var on = index === aspectIndex;
          button.style.cssText = "height:32px;padding:0 12px;border-radius:999px;border:1px solid " + (on ? "var(--color-x-blue)" : "var(--color-x-border)") + ";background:" + (on ? "var(--color-x-blue)" : "transparent") + ";color:" + (on ? "#fff" : "var(--color-x-ink)") + ";font:700 13px/1 Inter,sans-serif;cursor:pointer;";
          button.addEventListener("click", function () {
            aspectIndex = index;
            layoutFrame(true);
          });
          aspectsRow.appendChild(button);
        });
      }

      function setZoom(next, anchorX, anchorY) {
        var prev = scale;
        zoom = Math.min(3, Math.max(1, next));
        slider.value = String(zoom);
        var pointX = anchorX == null ? frameW / 2 : anchorX;
        var pointY = anchorY == null ? frameH / 2 : anchorY;
        var relX = (pointX - offsetX) / prev;
        var relY = (pointY - offsetY) / prev;
        scale = base * zoom;
        offsetX = pointX - relX * scale;
        offsetY = pointY - relY * scale;
        clamp();
        place();
      }

      function close(result) {
        if (settled) return;
        settled = true;
        document.removeEventListener("keydown", onKey);
        window.removeEventListener("resize", onResize);
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        document.body.style.overflow = previousOverflow;
        URL.revokeObjectURL(url);
        resolve(result);
      }

      function onKey(event) {
        if (event.key === "Escape") close(null);
      }

      function onResize() {
        layoutFrame(false);
      }

      var drag = null;
      viewport.addEventListener("pointerdown", function (event) {
        drag = { x: event.clientX, y: event.clientY, ox: offsetX, oy: offsetY };
        viewport.style.cursor = "grabbing";
        viewport.setPointerCapture(event.pointerId);
      });
      viewport.addEventListener("pointermove", function (event) {
        if (!drag) return;
        offsetX = drag.ox + (event.clientX - drag.x);
        offsetY = drag.oy + (event.clientY - drag.y);
        clamp();
        place();
      });
      function endDrag() {
        drag = null;
        viewport.style.cursor = "grab";
      }
      viewport.addEventListener("pointerup", endDrag);
      viewport.addEventListener("pointercancel", endDrag);
      viewport.addEventListener("wheel", function (event) {
        event.preventDefault();
        var rect = viewport.getBoundingClientRect();
        var delta = event.deltaY < 0 ? 0.08 : -0.08;
        setZoom(zoom + delta, event.clientX - rect.left, event.clientY - rect.top);
      }, { passive: false });
      slider.addEventListener("input", function () {
        setZoom(Number(slider.value));
      });
      cancel.addEventListener("click", function () { close(null); });
      apply.addEventListener("click", function () {
        apply.disabled = true;
        var sw = frameW / scale;
        var sh = frameH / scale;
        var sx = Math.max(0, -offsetX / scale);
        var sy = Math.max(0, -offsetY / scale);
        sw = Math.min(sw, nw - sx);
        sh = Math.min(sh, nh - sy);
        var outW = Math.max(1, Math.round(sw));
        var outH = Math.max(1, Math.round(sh));
        var longest = Math.max(outW, outH);
        if (longest > 1600) {
          var down = 1600 / longest;
          outW = Math.max(1, Math.round(outW * down));
          outH = Math.max(1, Math.round(outH * down));
        }
        var canvas = document.createElement("canvas");
        canvas.width = outW;
        canvas.height = outH;
        canvas.getContext("2d").drawImage(image, sx, sy, sw, sh, 0, 0, outW, outH);
        var type = kind === "image/png" ? "image/png" : kind === "image/webp" ? "image/webp" : "image/jpeg";
        canvas.toBlob(function (blob) {
          if (!blob) {
            close(null);
            return;
          }
          var baseName = String(file.name || "photo").replace(/\.[^.]+$/, "") || "photo";
          var ext = type === "image/png" ? ".png" : type === "image/webp" ? ".webp" : ".jpg";
          close(new File([blob], baseName + ext, { type: type, lastModified: Date.now() }));
        }, type, type === "image/png" ? undefined : 0.92);
      });
      document.addEventListener("keydown", onKey);
      window.addEventListener("resize", onResize);
      layoutFrame(true);
      apply.focus();
    }
  });
}
