/* ==========================================================================
   GoodsHub — interface behaviour
   Theme, navigation, counters, live metrics, dialogs, drop zones, flow control
   ========================================================================== */
(function () {
  "use strict";

  const root = document.documentElement;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- theme ---------- */
  const THEME_KEY = "goodshub.theme";

  function effectiveTheme() {
    if (root.dataset.theme === "light" || root.dataset.theme === "dark") {
      return root.dataset.theme;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") root.dataset.theme = stored;
  } catch (error) { /* storage blocked */ }

  function paintThemeButton(button) {
    const dark = effectiveTheme() === "dark";
    button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    button.innerHTML = dark
      ? '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17L5.6 18.4"/></svg>'
      : '<svg viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></svg>';
  }

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-theme-toggle]");
    if (!toggle) return;
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch (error) { /* ignore */ }
    paintThemeButton(toggle);
    document.dispatchEvent(new CustomEvent("goodshub:theme", { detail: next }));
  });

  document.querySelectorAll("[data-theme-toggle]").forEach(paintThemeButton);

  /* ---------- mobile navigation ---------- */
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-nav-toggle]")) {
      document.body.classList.toggle("nav-open");
      return;
    }
    if (event.target.closest("[data-nav-close]")) {
      document.body.classList.remove("nav-open");
      return;
    }
    const link = event.target.closest(".side .nav-item, .side .brand");
    if (link) document.body.classList.remove("nav-open");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") document.body.classList.remove("nav-open");
  });

  /* ---------- live clock ---------- */
  const clock = document.querySelector("[data-clock]");
  if (clock) {
    const tick = () => {
      const now = new Date();
      clock.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    };
    tick();
    setInterval(tick, 30000);
  }

  /* ---------- reveal on scroll ---------- */
  const revealItems = Array.from(document.querySelectorAll("[data-reveal]"));
  if ("IntersectionObserver" in window && !reduceMotion) {
    const groups = new Map();
    revealItems.forEach((item) => {
      const parent = item.parentElement;
      const list = groups.get(parent) || [];
      list.push(item);
      groups.set(parent, list);
    });
    groups.forEach((list) => {
      list.forEach((item, index) => {
        item.style.transitionDelay = Math.min(index * 55, 380) + "ms";
      });
    });

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.08 });

    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("in"));
  }

  /* ---------- count-up numbers ---------- */
  function countUp(node) {
    const target = Number(node.dataset.count);
    if (!Number.isFinite(target)) return;
    const decimals = Number(node.dataset.decimals || 0);
    const suffix = node.dataset.suffix || "";
    const prefix = node.dataset.prefix || "";

    if (reduceMotion) {
      node.textContent = prefix + target.toFixed(decimals) + suffix;
      return;
    }

    const duration = 1100;
    const start = performance.now();
    const from = 0;

    function step(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const value = from + (target - from) * eased;
      const text = value.toFixed(decimals);
      node.textContent = prefix + (decimals === 0 ? Number(text).toLocaleString() : text) + suffix;
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  const counters = Array.from(document.querySelectorAll("[data-count]"));
  if (counters.length && "IntersectionObserver" in window) {
    const counterObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          countUp(entry.target);
          counterObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.35 });
    counters.forEach((node) => counterObserver.observe(node));
  } else {
    counters.forEach(countUp);
  }

  /* ---------- flash messages ---------- */
  document.querySelectorAll(".flash").forEach((flash) => {
    const close = document.createElement("button");
    close.className = "x";
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss message");
    close.textContent = "✕";
    close.addEventListener("click", () => flash.remove());
    flash.appendChild(close);
    setTimeout(() => {
      flash.style.transition = "opacity .4s, transform .4s";
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-4px)";
      setTimeout(() => flash.remove(), 420);
    }, 6500);
  });

  /* ---------- confirm dialog ---------- */
  let dialog = null;

  function buildDialog() {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.setAttribute("role", "dialog");
    back.setAttribute("aria-modal", "true");
    back.innerHTML =
      '<div class="modal">' +
      '<h3 data-dlg-title>Confirm</h3>' +
      '<p data-dlg-text></p>' +
      '<div class="modal-actions">' +
      '<button type="button" class="btn ghost small" data-dlg-cancel>Cancel</button>' +
      '<button type="button" class="btn small" data-dlg-ok>Confirm</button>' +
      "</div></div>";
    document.body.appendChild(back);
    return back;
  }

  function confirmAction({ title, text, ok = "Confirm", danger = false }) {
    return new Promise((resolve) => {
      if (!dialog) dialog = buildDialog();
      dialog.querySelector("[data-dlg-title]").textContent = title;
      dialog.querySelector("[data-dlg-text]").textContent = text;
      const okBtn = dialog.querySelector("[data-dlg-ok]");
      const cancelBtn = dialog.querySelector("[data-dlg-cancel]");
      okBtn.textContent = ok;
      okBtn.classList.toggle("danger", danger);

      const finish = (value) => {
        dialog.classList.remove("on");
        document.removeEventListener("keydown", onKey);
        okBtn.removeEventListener("click", onOk);
        cancelBtn.removeEventListener("click", onCancel);
        if (value) resolve(true);
      };
      const onOk = () => finish(true);
      const onCancel = () => finish(false);
      const onKey = (event) => {
        if (event.key === "Escape") finish(false);
      };

      okBtn.addEventListener("click", onOk);
      cancelBtn.addEventListener("click", onCancel);
      document.addEventListener("keydown", onKey);
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) finish(false);
      });

      requestAnimationFrame(() => dialog.classList.add("on"));
    });
  }

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!form.dataset.confirm) return;
    event.preventDefault();
    const accepted = await confirmAction({
      title: form.dataset.confirmTitle || "Please confirm",
      text: form.dataset.confirm,
      ok: form.dataset.confirmOk || "Continue",
      danger: form.dataset.confirmDanger === "1",
    });
    if (accepted) {
      form.dataset.confirm = "";
      form.submit();
    }
  });

  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-confirm-link]");
    if (!trigger) return;
    event.preventDefault();
    const accepted = await confirmAction({
      title: trigger.dataset.confirmTitle || "Please confirm",
      text: trigger.dataset.confirmLink,
      ok: trigger.dataset.confirmOk || "Continue",
      danger: trigger.dataset.confirmDanger === "1",
    });
    if (accepted) window.location.href = trigger.getAttribute("href");
  });

  /* ---------- drop zones ---------- */
  document.querySelectorAll(".dropzone").forEach((zone) => {
    const input = zone.querySelector('input[type="file"]');
    const name = zone.querySelector(".dz-name");
    if (!input) return;

    input.addEventListener("change", () => {
      if (name && input.files && input.files.length) {
        name.textContent = input.files[0].name;
        zone.classList.add("has-file");
      }
    });

    ["dragenter", "dragover"].forEach((type) => {
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach((type) => {
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.remove("drag");
      });
    });
  });

  /* ---------- flow animation control ---------- */
  document.querySelectorAll("[data-flow-toggle]").forEach((control) => {
    const scopeSelector = control.dataset.flowToggle || ".flow-svg";
    const label = control.querySelector("[data-flow-label]");
    let paused = false;

    control.addEventListener("click", () => {
      paused = !paused;
      document.querySelectorAll(scopeSelector).forEach((svg) => {
        svg.classList.toggle("flow-paused", paused);
        if (typeof svg.pauseAnimations === "function") {
          if (paused) svg.pauseAnimations();
          else svg.unpauseAnimations();
        }
      });
      control.classList.toggle("paused", paused);
      if (label) label.textContent = paused ? "Resume flow" : "Pause flow";
      control.setAttribute("aria-pressed", String(paused));
    });
  });

  /* ---------- live metrics ---------- */
  const liveNodes = Array.from(document.querySelectorAll("[data-live]"));
  const liveUrl = document.body.dataset.liveUrl;

  if (liveUrl && liveNodes.length) {
    const statusDot = document.querySelector("[data-live-status]");

    const paint = (payload) => {
      liveNodes.forEach((node) => {
        const key = node.dataset.live;
        if (!(key in payload)) return;
        const next = payload[key];
        const current = node.textContent.replace(/[^0-9.-]/g, "");
        const value = typeof next === "number" ? next : Number(next);
        if (!Number.isFinite(value)) {
          node.textContent = next;
          return;
        }
        if (Number(current) === value) return;
        const decimals = Number(node.dataset.decimals || 0);
        const suffix = node.dataset.suffix || "";
        node.textContent = (decimals ? value.toFixed(decimals) : value.toLocaleString()) + suffix;
        node.classList.remove("pulse-once");
        void node.offsetWidth;
        node.classList.add("pulse-once");
      });

      if (statusDot) {
        statusDot.textContent = "live";
        statusDot.classList.add("ok");
      }
    };

    const poll = async () => {
      try {
        const response = await fetch(liveUrl, { headers: { Accept: "application/json" }, cache: "no-store" });
        if (!response.ok) throw new Error("status " + response.status);
        const payload = await response.json();
        paint(payload);
      } catch (error) {
        if (statusDot) {
          statusDot.textContent = "offline";
          statusDot.classList.remove("ok");
        }
      }
    };

    poll();
    setInterval(poll, 6000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) poll();
    });
  }

  /* ---------- table row highlight ---------- */
  document.querySelectorAll("tbody tr[data-href]").forEach((row) => {
    row.style.cursor = "pointer";
    row.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input, form, label")) return;
      window.location.href = row.dataset.href;
    });
  });

  /* ---------- pause flow when tab hidden ---------- */
  document.addEventListener("visibilitychange", () => {
    document.querySelectorAll(".flow-svg").forEach((svg) => {
      if (typeof svg.pauseAnimations !== "function") return;
      if (document.hidden) svg.pauseAnimations();
      else if (!svg.classList.contains("flow-paused")) svg.unpauseAnimations();
    });
  });
})();
