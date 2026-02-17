function showNotice(msg, ms = 2000, type = "info") {
  const el = document.getElementById("notice-toast");
  if (!el) return;

  el.textContent = msg;

  // ustaw klasę zależnie od typu
  el.classList.toggle("notice-error", type === "error");
  el.classList.toggle("notice-info", type === "info");

  el.style.opacity = "1";
  clearTimeout(window.__noticeTimer);
  window.__noticeTimer = setTimeout(() => {
    el.style.opacity = "0";
    el.classList.remove("notice-error"); // posprzątaj po zniknięciu
  }, ms);
}



document.addEventListener('DOMContentLoaded', () => {
    const shareLinks = document.querySelectorAll('.share-link');
    
    shareLinks.forEach(link => {
        const modalId = link.dataset.modal;
        const modal = document.getElementById(modalId);
        const overlay = modal.querySelector('.share-modal-overlay');
        const copyBtn = modal.querySelector('.copy-link');

        // otwieranie modala
        link.addEventListener('click', e => {
            e.preventDefault();
            modal.style.display = 'block';
            document.body.classList.add('modal-open');
        });

        // zamykanie modala po kliknięciu w overlay
        overlay.addEventListener('click', () => closeModal(modal));

        // zamykanie modala po kliknięciu dowolnego linku (oprócz kopiuj)
        modal.querySelectorAll('.share-buttons a').forEach(a => {
            if (!a.classList.contains('copy-link')) {
                a.addEventListener('click', () => closeModal(modal));
            }
        });

        // kopiowanie linku
        copyBtn.addEventListener('click', e => {
            e.preventDefault();
            const linkToCopy = copyBtn.dataset.link;
            navigator.clipboard.writeText(linkToCopy).then(() => {
                closeModal(modal);
                showNotice("Link skopiowany do schowka", 2000);
            });
        });
    });

    function closeModal(modal) {
        modal.style.display = 'none';
        document.body.classList.remove('modal-open');
    }

    
});

document.addEventListener("DOMContentLoaded", function () {
    const textarea = document.getElementById("comment-content");
    const counter = document.getElementById("chars-left");
    const maxLength = 200;

    if (!textarea || !counter) return;

    function updateCounter() {
        const currentLength = textarea.value.length;
        const remaining = maxLength - currentLength;
        counter.textContent = remaining;
    }

    // na start
    updateCounter();

    // przy każdym wpisaniu znaku
    textarea.addEventListener("input", updateCounter);
});

document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("scroll-top");
    const topAnchor = document.getElementById("content-top");
    if (!btn || !topAnchor) return;

    const showAfterPx = 200;

    function updateVisibility() {
        btn.hidden = window.scrollY < showAfterPx;
    }

    function scrollToTop() {
        topAnchor.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    btn.addEventListener("click", scrollToTop);
    btn.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            scrollToTop();
        }
    });

    window.addEventListener("scroll", updateVisibility, { passive: true });
    updateVisibility();
});


document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector(".searchbox-widget input[name='q']");
  if (!input) return;

  input.addEventListener("focus", () => {
    input.value = "";
  });

  // opcjonalnie: po kliknięciu poza inputem, jak jest puste, wróć do query z serwera
  input.addEventListener("blur", () => {
    if (input.value.trim() === "") {
      input.value = input.getAttribute("value") || "";
    }
  });
});

document.addEventListener("DOMContentLoaded", () => {
    const sel = document.getElementById("categories-list");
    if (!sel) return;

    sel.addEventListener("change", () => {
      const v = sel.value;
      if (!v) return;
      window.location.href = "/kategorie/" + encodeURIComponent(v);
    });
  });

(() => {
  const COOKIE_NAME = "cookie_consent_ack";
  const modal = document.getElementById("cookieConsent");
  const okBtn = document.getElementById("cookieConsentOk");
  if (!modal || !okBtn) return;

  function getCookie(name){
    const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function setConsentCookie(){
    // ~10 lat ważności (praktycznie "do skasowania cookies")
    const d = new Date();
    d.setFullYear(d.getFullYear() + 10);

    const secure = (location.protocol === "https:") ? "; Secure" : "";
    document.cookie =
      COOKIE_NAME + "=1" +
      "; Expires=" + d.toUTCString() +
      "; Path=/" +
      "; SameSite=Lax" +
      secure;
  }

  // pokaż modal tylko jeśli nie ma cookie
  if (!getCookie(COOKIE_NAME)) {
    modal.hidden = false;
    setTimeout(() => okBtn.focus(), 0);
  }

  okBtn.addEventListener("click", () => {
    setConsentCookie();
    modal.hidden = true;
  });
})();


document.addEventListener("DOMContentLoaded", () => {
  const url = new URL(window.location.href);
  let changed = false;

  // ✅ kontakt: wiadomość wysłana
  if (url.searchParams.get("sent") === "1") {
    showNotice("Wiadomość wysłana. Dzięki!", 2200, "info");
    url.searchParams.delete("sent");
    changed = true;
  }

  // ❌ captcha
  if (url.searchParams.get("captcha") === "1") {
    showNotice("Błąd captcha. Spróbuj ponownie.", 2500, "error");
    url.searchParams.delete("captcha");
    changed = true;
  }

  // ⏳ cooldown
  const cd = url.searchParams.get("cooldown"); // string albo null
  if (cd !== null) {
    const seconds = parseInt(cd, 10);
    if (Number.isFinite(seconds) && seconds > 0) {
      showNotice(`Za szybko. Spróbuj ponownie za ${seconds}s.`, 3500, "error");
    }
    url.searchParams.delete("cooldown");
    changed = true;
  }

  // usuń parametry, żeby po F5 nie pokazywało znowu
  if (changed) {
    const clean =
      url.pathname +
      (url.searchParams.toString() ? "?" + url.searchParams.toString() : "") +
      (url.hash || "");
    window.history.replaceState({}, "", clean);
  }
});



 const ta = document.getElementById("contact-message");
  const left = document.getElementById("chars-left");
  if (ta && left) {
    const max = ta.getAttribute("maxlength") ? parseInt(ta.getAttribute("maxlength"), 10) : 1000;
    left.textContent = String(max);
    const update = () => left.textContent = String(Math.max(0, max - ta.value.length));
    ta.addEventListener("input", update);
    update();
  }

  (function () {
  const backdrop = document.querySelector('.drawer-backdrop');
  const buttons = document.querySelectorAll('[data-drawer]');

  if (!backdrop || !buttons.length) return;

  function closeDrawer() {
    document.body.classList.remove('drawer-open', 'drawer-sidebar', 'drawer-widgets');
    backdrop.hidden = true;
    buttons.forEach(b => b.setAttribute('aria-expanded', 'false'));
  }

  function openDrawer(which) {
  // wyczyść stan
  document.body.classList.remove('drawer-open', 'drawer-sidebar', 'drawer-widgets');

  // ustaw nowy stan
  document.body.classList.add('drawer-open');
  document.body.classList.add(which === 'sidebar' ? 'drawer-sidebar' : 'drawer-widgets');

  backdrop.hidden = false;

  buttons.forEach(b => {
    b.setAttribute('aria-expanded', b.dataset.drawer === which ? 'true' : 'false');
  });
}


  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const which = btn.dataset.drawer;
      const isOpen = document.body.classList.contains('drawer-open') &&
                     document.body.classList.contains(which === 'sidebar' ? 'drawer-sidebar' : 'drawer-widgets');

      if (isOpen) closeDrawer();
      else openDrawer(which);
    });
  });

  backdrop.addEventListener('click', closeDrawer);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
  });

  // bezpieczeństwo: po przekroczeniu breakpointu wyczyść stan
  const mq = window.matchMedia('(max-width: 980px)');
  mq.addEventListener?.('change', (e) => { if (!e.matches) closeDrawer(); });
})();

document.addEventListener("DOMContentLoaded", () => {
  const overlay = document.getElementById("loading-overlay");
  if (!overlay) return;

  function showLoading() {
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open"); // opcjonalnie blokuje scroll jeśli używasz
  }

  // Kontakt
  const contactForm = document.querySelector('form[action^="/kontakt"]');
  if (contactForm) {
    contactForm.addEventListener("submit", () => {
      showLoading();
    });
  }

  // Komentarze (jeśli chcesz też tutaj)
  const commentForm = document.querySelector('form[action*="/comment"]');
  if (commentForm) {
    commentForm.addEventListener("submit", () => {
      showLoading();
    });
  }
});
(function () {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/[$()*+.?[\\\]^{|}-]/g, "\\$&") + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function registerPostViewOncePer24h({ postSlug, postId, identity, endpointBase = "" }) {
    try {
      if (!postSlug || !postId || !identity) return;

      const DAY_MS = 24 * 60 * 60 * 1000;
      const key = `pv:${identity}:${postId}`;
      const now = Date.now();

      const last = parseInt(localStorage.getItem(key) || "0", 10);
      if (Number.isFinite(last) && last > 0 && (now - last) < DAY_MS) return;

      localStorage.setItem(key, String(now));

      fetch(`${endpointBase}/post/${encodeURIComponent(postSlug)}/view`, {
        method: "POST",
        headers: { "Content-Type": "text/plain" },
        keepalive: true,
      }).catch(() => {});
    } catch (_) {}
  }

  document.addEventListener("DOMContentLoaded", () => {
    // tylko publiczne dane posta w HTML
    const el = document.querySelector("[data-post='1'][data-post-id][data-post-slug]");
    if (!el) return;

    const postId = el.getAttribute("data-post-id");
    const postSlug = el.getAttribute("data-post-slug");

    // identyfikator: vid (jeśli czytelne) albo visitor_id
    const identity = getCookie("vid") || getCookie("visitor_id");
    if (!identity) return;

    registerPostViewOncePer24h({ postSlug, postId, identity });
  });
})();
