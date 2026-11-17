/* Blocks the page behind a provider + API-key prompt until /api/set-key
 * validates the user's own key. If keys are in .env, the modal is automatically
 * bypassed. The key can also be kept in browser sessionStorage across reloads.
 * Supports comma-separated keys for automatic round-robin and failover. */
(function () {
  "use strict";

  var STORAGE_KEY = "qa_llm_key_session";
  var STYLE =
    "#llm-key-modal-overlay{position:fixed;inset:0;background:rgba(10,12,20,.82);" +
    "backdrop-filter:blur(6px);z-index:99999;display:flex;align-items:center;" +
    "justify-content:center;font-family:system-ui,-apple-system,sans-serif}" +
    "#llm-key-modal{background:#151824;color:#e2e8f0;border-radius:14px;padding:26px 28px;" +
    "width:430px;max-width:92vw;box-shadow:0 24px 64px rgba(0,0,0,.65);border:1px solid #232b42}" +
    "#llm-key-modal h2{margin:0 0 6px;font-size:18px;font-weight:700;letter-spacing:-0.01em;display:flex;align-items:center;gap:8px}" +
    "#llm-key-modal p{margin:0 0 16px;font-size:12.5px;color:#94a3b8;line-height:1.45}" +
    "#llm-key-modal .provider-row{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}" +
    "#llm-key-modal .provider-btn{flex:1 1 calc(33.333% - 6px);min-width:76px;padding:9px 6px;border-radius:8px;" +
    "border:1px solid #28334e;background:#1a2032;color:#cbd5e1;cursor:pointer;font-size:12.5px;font-weight:600;" +
    "transition:all .15s ease;display:flex;align-items:center;justify-content:center;gap:5px}" +
    "#llm-key-modal .provider-btn:hover{background:#222b44;color:#fff;border-color:#3b82f6}" +
    "#llm-key-modal .provider-btn.selected{border-color:#6366f1;background:#242848;color:#a5b4fc;box-shadow:0 0 0 1px #6366f1}" +
    "#llm-key-modal input[type=password]{width:100%;box-sizing:border-box;padding:10px 12px;" +
    "border-radius:8px;border:1px solid #28334e;background:#0d111a;color:#f1f5f9;font-size:13px;margin-bottom:10px;" +
    "transition:border-color .15s ease;outline:none}" +
    "#llm-key-modal input[type=password]:focus{border-color:#6366f1}" +
    "#llm-key-modal .help-tip{font-size:11.5px;color:#64748b;margin:-4px 0 12px;line-height:1.35}" +
    "#llm-key-modal button.submit{width:100%;padding:10.5px;border-radius:8px;border:none;" +
    "background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;font-size:13.5px;font-weight:600;cursor:pointer;" +
    "box-shadow:0 4px 12px rgba(99,102,241,.3);transition:all .15s ease}" +
    "#llm-key-modal button.submit:hover:not(:disabled){background:linear-gradient(135deg,#4f46e5,#4338ca)}" +
    "#llm-key-modal button.submit:disabled{opacity:.45;cursor:default;box-shadow:none}" +
    "#llm-key-modal .error{color:#f87171;font-size:12px;margin:-4px 0 10px;min-height:16px;line-height:1.35}";

  function savedKey() {
    try {
      var saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
      if (saved && saved.provider && saved.api_key) return saved;
    } catch (e) {}
    return null;
  }

  function storeKey(provider, apiKey) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ provider: provider, api_key: apiKey }));
    } catch (e) {}
  }

  function clearKey() {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
  }

  function setKey(provider, apiKey) {
    return fetch("/api/set-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: provider, api_key: apiKey }),
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    });
  }

  function installRetryFetch() {
    var originalFetch = window.fetch;
    window.fetch = function (url, opts) {
      var path = (typeof url === "string" ? url : (url && url.url) || "").split("?")[0];
      var isSetKey = path === "/api/set-key" || path.endsWith("/api/set-key");
      var isKeyStatus = path === "/api/key-status" || path.endsWith("/api/key-status");

      return originalFetch.apply(this, arguments).then(function (response) {
        if (isSetKey || isKeyStatus || response.status !== 401) return response;

        return response.clone().json().then(function (data) {
          var detail = String((data && data.detail) || "");
          var saved = savedKey();
          if (detail.indexOf("No LLM key set") === -1 || !saved) return response;

          return originalFetch("/api/set-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(saved),
          }).then(function (keyResponse) {
            if (!keyResponse.ok) return response;
            return originalFetch(url, opts);
          });
        }).catch(function () {
          return response;
        });
      });
    };
  }

  function init() {
    installRetryFetch();

    var styleEl = document.createElement("style");
    styleEl.textContent = STYLE;
    document.head.appendChild(styleEl);

    var overlay = document.createElement("div");
    overlay.id = "llm-key-modal-overlay";
    overlay.innerHTML =
      '<div id="llm-key-modal">' +
      "<h2><span>🔑</span> Connect AI Provider</h2>" +
      "<p>Pick a provider and enter your API key. Multiple keys separated by comma will automatically round-robin and failover.</p>" +
      '<div class="provider-row">' +
      '<button type="button" class="provider-btn" data-provider="groq">Groq</button>' +
      '<button type="button" class="provider-btn" data-provider="openai">OpenAI</button>' +
      '<button type="button" class="provider-btn" data-provider="gemini">Gemini</button>' +
      '<button type="button" class="provider-btn" data-provider="claude">Claude</button>' +
      '<button type="button" class="provider-btn" data-provider="codevector">CodeVector</button>' +
      "</div>" +
      '<input type="password" id="llm-key-input" placeholder="API key (or key1, key2 for round-robin)" autocomplete="off" style="display:none" />' +
      '<div class="help-tip" id="llm-key-tip" style="display:none">Tip: You can add keys to .env to skip this prompt entirely.</div>' +
      '<div class="error" id="llm-key-error"></div>' +
      '<button type="button" class="submit" id="llm-key-submit" disabled>Continue</button>' +
      "</div>";

    // First check if the backend already has keys initialized from .env
    fetch("/api/key-status")
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (data && data.configured) {
          // Already configured in backend (e.g. via .env) — modal not required
          return;
        }
        mountModal();
      })
      .catch(function () {
        mountModal();
      });

    function mountModal() {
      if (document.getElementById("llm-key-modal-overlay")) return;
      document.body.appendChild(overlay);

      var selected = null;
      var buttons = overlay.querySelectorAll(".provider-btn");
      var input = overlay.querySelector("#llm-key-input");
      var tip = overlay.querySelector("#llm-key-tip");
      var submitBtn = overlay.querySelector("#llm-key-submit");
      var errorEl = overlay.querySelector("#llm-key-error");

      function updateSubmitState() {
        submitBtn.disabled = !(selected && input.value.trim());
      }

      buttons.forEach(function (btn) {
        btn.addEventListener("click", function () {
          selected = btn.getAttribute("data-provider");
          buttons.forEach(function (b) { b.classList.remove("selected"); });
          btn.classList.add("selected");
          input.style.display = "block";
          if (tip) tip.style.display = "block";
          input.focus();
          updateSubmitState();
        });
      });

      function submit() {
        if (submitBtn.disabled) return;
        submitBtn.disabled = true;
        submitBtn.textContent = "Checking...";
        errorEl.textContent = "";

        setKey(selected, input.value.trim())
          .then(function (res) {
            if (res.ok) {
              storeKey(selected, input.value.trim());
              if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
            } else {
              clearKey();
              errorEl.textContent = (res.data && res.data.detail) || "Could not validate this key.";
              submitBtn.disabled = false;
              submitBtn.textContent = "Continue";
            }
          })
          .catch(function () {
            errorEl.textContent = "Network error - is the server running?";
            submitBtn.disabled = false;
            submitBtn.textContent = "Continue";
          });
      }

      input.addEventListener("input", updateSubmitState);
      submitBtn.addEventListener("click", submit);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") submit();
      });

      var saved = savedKey();
      if (saved) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Restoring...";
        setKey(saved.provider, saved.api_key)
          .then(function (res) {
            if (res.ok) {
              if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
            } else {
              clearKey();
              submitBtn.disabled = false;
              submitBtn.textContent = "Continue";
              errorEl.textContent = "Saved key was rejected. Paste it again.";
            }
          })
          .catch(function () {
            submitBtn.disabled = false;
            submitBtn.textContent = "Continue";
            errorEl.textContent = "Network error - is the server running?";
          });
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
