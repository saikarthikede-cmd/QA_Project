/* Blocks the page behind a provider + API-key prompt until /api/set-key
 * validates the user's own key. Held in memory only (no localStorage) — a
 * fresh page load always asks again, matching the per-app key isolation
 * the backend already uses (each app's .env used to be independent too). */
(function () {
  "use strict";

  var STYLE =
    "#llm-key-modal-overlay{position:fixed;inset:0;background:rgba(15,15,20,.75);" +
    "backdrop-filter:blur(2px);z-index:99999;display:flex;align-items:center;" +
    "justify-content:center;font-family:system-ui,-apple-system,sans-serif}" +
    "#llm-key-modal{background:#1c1c24;color:#eee;border-radius:12px;padding:28px 32px;" +
    "width:360px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,.5)}" +
    "#llm-key-modal h2{margin:0 0 6px;font-size:18px}" +
    "#llm-key-modal p{margin:0 0 18px;font-size:13px;color:#aaa}" +
    "#llm-key-modal .provider-row{display:flex;gap:10px;margin-bottom:16px}" +
    "#llm-key-modal .provider-btn{flex:1;padding:12px 8px;border-radius:8px;" +
    "border:2px solid #333;background:#262630;color:#eee;cursor:pointer;font-size:14px;font-weight:600}" +
    "#llm-key-modal .provider-btn.selected{border-color:#6366f1;background:#2b2b45}" +
    "#llm-key-modal input[type=password]{width:100%;box-sizing:border-box;padding:10px 12px;" +
    "border-radius:8px;border:1px solid #333;background:#14141a;color:#eee;font-size:14px;margin-bottom:12px}" +
    "#llm-key-modal button.submit{width:100%;padding:11px;border-radius:8px;border:none;" +
    "background:#6366f1;color:#fff;font-size:14px;font-weight:600;cursor:pointer}" +
    "#llm-key-modal button.submit:disabled{opacity:.5;cursor:default}" +
    "#llm-key-modal .error{color:#f87171;font-size:13px;margin:-4px 0 12px;min-height:16px}";

  function init() {
    var styleEl = document.createElement("style");
    styleEl.textContent = STYLE;
    document.head.appendChild(styleEl);

    var overlay = document.createElement("div");
    overlay.id = "llm-key-modal-overlay";
    overlay.innerHTML =
      '<div id="llm-key-modal">' +
      "<h2>Connect your LLM key</h2>" +
      "<p>Pick a provider and paste your own API key. It's used only for this session and never stored.</p>" +
      '<div class="provider-row">' +
      '<button type="button" class="provider-btn" data-provider="groq">Groq</button>' +
      '<button type="button" class="provider-btn" data-provider="openai">OpenAI</button>' +
      "</div>" +
      '<input type="password" id="llm-key-input" placeholder="API key" autocomplete="off" style="display:none" />' +
      '<div class="error" id="llm-key-error"></div>' +
      '<button type="button" class="submit" id="llm-key-submit" disabled>Continue</button>' +
      "</div>";
    document.body.appendChild(overlay);

    var selected = null;
    var buttons = overlay.querySelectorAll(".provider-btn");
    var input = overlay.querySelector("#llm-key-input");
    var submitBtn = overlay.querySelector("#llm-key-submit");
    var errorEl = overlay.querySelector("#llm-key-error");

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        selected = btn.getAttribute("data-provider");
        buttons.forEach(function (b) { b.classList.remove("selected"); });
        btn.classList.add("selected");
        input.style.display = "block";
        input.focus();
        updateSubmitState();
      });
    });

    input.addEventListener("input", updateSubmitState);
    function updateSubmitState() {
      submitBtn.disabled = !(selected && input.value.trim());
    }

    function submit() {
      if (submitBtn.disabled) return;
      submitBtn.disabled = true;
      submitBtn.textContent = "Checking...";
      errorEl.textContent = "";
      fetch("/api/set-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: selected, api_key: input.value.trim() }),
      })
        .then(function (r) {
          return r.json().then(function (data) { return { ok: r.ok, data: data }; });
        })
        .then(function (res) {
          if (res.ok) {
            overlay.remove();
          } else {
            errorEl.textContent = (res.data && res.data.detail) || "Could not validate this key.";
            submitBtn.disabled = false;
            submitBtn.textContent = "Continue";
          }
        })
        .catch(function () {
          errorEl.textContent = "Network error — is the server running?";
          submitBtn.disabled = false;
          submitBtn.textContent = "Continue";
        });
    }

    submitBtn.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submit();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
