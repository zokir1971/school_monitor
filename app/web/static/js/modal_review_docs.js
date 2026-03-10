/* ======================================================
   Modal logic:
   - required documents
   - review places
====================================================== */

document.addEventListener("click", (e) => {
  const docsBtn = e.target.closest(".js-open-docs");
  if (docsBtn) {
    openDocsModal(docsBtn);
    return;
  }

  const reviewBtn = e.target.closest(".js-open-review");
  if (reviewBtn) {
    openReviewModal(reviewBtn);
  }
});


/* ======================================================
   OPEN MODALS
====================================================== */

function openDocsModal(btn) {
  const form = document.getElementById("docsForm");
  if (!form) {
    console.error("docsForm not found");
    return;
  }

  form.action = btn.dataset.action || "";
  form.dataset.rowId = btn.dataset.rowId || "";

  const selected = parseJsonArray(btn.dataset.docs);
  document.querySelectorAll(".docsChk").forEach((ch) => {
    ch.checked = selected.includes(ch.value);
  });

  openModal("docsModal");
}

function openReviewModal(btn) {
  const form = document.getElementById("reviewForm");
  if (!form) {
    console.error("reviewForm not found");
    return;
  }

  form.action = btn.dataset.action || "";
  form.dataset.rowId = btn.dataset.rowId || "";

  const selected = parseJsonArray(btn.dataset.places);
  document.querySelectorAll(".reviewChk").forEach((ch) => {
    ch.checked = selected.includes(ch.value);
  });

  openModal("reviewModal");
}


/* ======================================================
   MODAL OPEN / CLOSE
====================================================== */

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;

  modal.classList.add("is-open");
  modal.setAttribute("aria-hidden", "false");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;

  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
}


/* ======================================================
   SUBMIT FORMS VIA FETCH
====================================================== */

document.addEventListener("submit", async (e) => {
  const form = e.target;

  if (form.id !== "docsForm" && form.id !== "reviewForm") {
    return;
  }

  e.preventDefault();

  const rowId = form.dataset.rowId;
  const formData = new FormData(form);

  try {
    const resp = await fetch(form.action, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    });

    const rawText = await resp.text();

    let data = null;
    try {
      data = JSON.parse(rawText);
    } catch {
      // Нормально: если сервер вернул redirect/html, отработает fallback
    }

    if (form.id === "docsForm") {
      const selectedDocs = formData.getAll("required_document_types");

      updateDocsBadges(rowId, data?.documents || selectedDocs);
      updateDocsButtonData(rowId, data?.documents || selectedDocs);
      closeModal("docsModal");
      return;
    }

    if (form.id === "reviewForm") {
      const selectedPlaces = formData.getAll("review_places");

      updateReviewBadges(rowId, data?.review_places || selectedPlaces);
      updateReviewButtonData(rowId, data?.review_places || selectedPlaces);
      closeModal("reviewModal");
    }

  } catch (err) {
    console.error("Fetch error:", err);
    alert("Сервер қатесі");
  }
});


/* ======================================================
   UPDATE BADGES
====================================================== */

function updateDocsBadges(rowId, values = []) {
  updateBadges({
    containerId: `docView_${rowId}`,
    values,
    labelGetter: getDocLabel
  });
}

function updateReviewBadges(rowId, values = []) {
  updateBadges({
    containerId: `reviewView_${rowId}`,
    values,
    labelGetter: getReviewLabel
  });
}

function updateBadges({ containerId, values = [], labelGetter }) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = "";

  if (!values.length) {
    container.innerHTML = '<span class="badge">-</span>';
    return;
  }

  values.forEach((value) => {
    appendBadge(container, labelGetter(value));
  });
}

function appendBadge(container, text) {
  const span = document.createElement("span");
  span.className = "badge";
  span.textContent = text;
  container.appendChild(span);
}


/* ======================================================
   UPDATE BUTTON DATA
====================================================== */

function updateDocsButtonData(rowId, values) {
  const btn = document.querySelector(`.js-open-docs[data-row-id="${rowId}"]`);
  if (!btn) return;

  btn.dataset.docs = JSON.stringify(values || []);
}

function updateReviewButtonData(rowId, values) {
  const btn = document.querySelector(`.js-open-review[data-row-id="${rowId}"]`);
  if (!btn) return;

  btn.dataset.places = JSON.stringify(values || []);
}


/* ======================================================
   LABEL HELPERS
====================================================== */

function getDocLabel(value) {
  return getLabelFromMap("docLabels", value);
}

function getReviewLabel(value) {
  return getLabelFromMap("reviewLabels", value);
}

function getLabelFromMap(elementId, value) {
  const el = document.getElementById(elementId);
  if (!el) return value;

  try {
    const map = JSON.parse(el.dataset.map || "{}");
    return map[value] || value;
  } catch {
    return value;
  }
}


/* ======================================================
   HELPERS
====================================================== */

function parseJsonArray(raw) {
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}


/* ======================================================
   EXPORT FUNCTIONS
====================================================== */

window.openDocsModal = openDocsModal;
window.openReviewModal = openReviewModal;
window.closeModal = closeModal;