document.addEventListener('DOMContentLoaded', () => {
    const shareLinks = document.querySelectorAll('.share-link');
    const copyNotice = document.getElementById('copy-notice');

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
                copyNotice.style.opacity = '1';
                setTimeout(() => copyNotice.style.opacity = '0', 2000);
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
