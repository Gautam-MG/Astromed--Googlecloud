/* Clerk session helper. Only the publishable key is loaded from the server. */
(function () {
  const originalFetch = window.fetch.bind(window);

  async function loadConfig() {
    const response = await originalFetch("/public-config");
    if (!response.ok) return {};
    return response.json();
  }

  function sameOrigin(input) {
    if (typeof input !== "string") return false;
    if (input.startsWith("/")) return true;
    try {
      return new URL(input, window.location.origin).origin === window.location.origin;
    } catch (_err) {
      return false;
    }
  }

  window.fetch = async function (input, init) {
    const next = init ? { ...init } : {};
    if (sameOrigin(input) && window.Clerk && window.Clerk.session) {
      const token = await window.Clerk.session.getToken();
      if (token) {
        const headers = new Headers(next.headers || {});
        if (!headers.has("Authorization")) headers.set("Authorization", "Bearer " + token);
        next.headers = headers;
      }
    }
    return originalFetch(input, next);
  };

  function openSignIn() {
    if (window.Clerk) window.Clerk.openSignIn();
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form || !form.classList || !form.classList.contains("birth-form")) return;
    if (!window.Clerk || !window.Clerk.user) {
      event.preventDefault();
      event.stopImmediatePropagation();
      openSignIn();
    }
  }, true);

  document.addEventListener("click", function (event) {
    const button = event.target.closest(".mobile-nav-toggle");
    if (!button) return;
    const links = document.querySelector(".nav-links");
    if (links) links.classList.toggle("open");
  });

  window.astromedicaSignOut = async function () {
    if (window.Clerk) await window.Clerk.signOut();
    window.location.href = "/";
  };

  loadConfig().then(async function (config) {
    const slot = document.getElementById("account-slot");
    if (!config.clerkPublishableKey) {
      if (slot) slot.textContent = "Sign-in is not configured";
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js";
    script.async = true;
    script.crossOrigin = "anonymous";
    script.setAttribute("data-clerk-publishable-key", config.clerkPublishableKey);
    script.addEventListener("load", async function () {
      await window.Clerk.load();
      if (slot && window.Clerk.user) {
        window.Clerk.mountUserButton(slot);
      } else if (slot) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Sign in";
        button.addEventListener("click", openSignIn);
        slot.replaceChildren(button);
        window.Clerk.addListener(function () {
          if (window.Clerk.user) {
            slot.replaceChildren();
            window.Clerk.mountUserButton(slot);
          }
        });
      }
    });
    document.head.appendChild(script);
  });
})();
