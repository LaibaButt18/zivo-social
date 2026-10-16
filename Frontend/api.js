var API = "http://127.0.0.1:5000";

function authHeaders() {
  var headers = { "Content-Type": "application/json" };
  var token = localStorage.getItem("zivo_token");
  if (token) {
    headers.Authorization = "Bearer " + token;
  }
  return headers;
}

function apiFetch(path, options) {
  options = options || {};
  options.headers = authHeaders();
  return fetch(API + path, options).then(function (response) {
    return response.text().then(function (text) {
      var data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (err) {
          data = { message: "Bad request. Try again." };
        }
      }
      return { ok: response.ok, status: response.status, data: data };
    });
  });
}

function apiForm(path, formData) {
  var headers = {};
  var token = localStorage.getItem("zivo_token");
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
          data = { message: "Bad request. Try again." };
        }
      }
      return { ok: response.ok, status: response.status, data: data };
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

function premiumMark() {
  var mark = document.createElement("span");
  mark.className = "inline-flex shrink-0 text-x-blue";
  mark.title = "Zivo Premium";
  mark.setAttribute("aria-label", "Premium");
  mark.innerHTML = '<svg viewBox="0 0 24 24" class="size-4" aria-hidden="true"><path fill="currentColor" d="M12 2.4 9.6 8.2 3.3 8.8l4.8 4.1-1.4 6.3L12 16.2l5.3 3 1.4-6.3 4.8-4.1-6.3-.6z"/></svg>';
  return mark;
}
