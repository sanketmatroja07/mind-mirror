async function getEntries() {
  const res = await fetch("/api/entries");
  return res.json();
}

function initThemeToggle() {
  const toggle = document.getElementById("themeToggle");
  if (!toggle) return;
  const root = document.body;
  const storageKey = "mind-mirror-theme";
  const savedTheme = localStorage.getItem(storageKey);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initial = savedTheme || (prefersDark ? "dark" : "light");
  root.setAttribute("data-theme", initial);
  toggle.innerHTML = initial === "dark" ? "&#9788;" : "&#9790;";

  toggle.addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem(storageKey, next);
    toggle.innerHTML = next === "dark" ? "&#9788;" : "&#9790;";
  });
}

function drawTrend(entries) {
  const svg = document.getElementById("trendChart");
  if (!svg) return;
  if (!entries.length) {
    svg.innerHTML = "";
    return;
  }

  const values = entries.map((e) => Number(e.sentiment.polarity) || 0);
  const width = 700;
  const height = 200;
  const padding = 28;
  const min = -1;
  const max = 1;
  const axisY = height - padding - ((0 - min) / (max - min)) * (height - padding * 2);

  const points = values.map((value, i) => {
    const x = padding + (i * (width - padding * 2)) / Math.max(1, values.length - 1);
    const y = height - padding - ((value - min) / (max - min)) * (height - padding * 2);
    return `${x},${y}`;
  });

  svg.innerHTML = `
    <line x1="${padding}" y1="${axisY}" x2="${width - padding}" y2="${axisY}" stroke="currentColor" opacity="0.15" stroke-width="1" stroke-dasharray="4,4" />
    <polyline fill="none" stroke="#4a9882" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${points.join(" ")}" />
    ${points
      .map((p) => {
        const [x, y] = p.split(",");
        return `<circle cx="${x}" cy="${y}" r="3.5" fill="#6b8cc7" stroke="#fff" stroke-width="1.5" />`;
      })
      .join("")}
  `;
}

function drawDistribution(entries) {
  const svg = document.getElementById("distributionChart");
  if (!svg) return;
  if (!entries.length) {
    svg.innerHTML = "";
    return;
  }

  const counts = { Positive: 0, Neutral: 0, Negative: 0 };
  for (const entry of entries) {
    counts[entry.sentiment.label] = (counts[entry.sentiment.label] || 0) + 1;
  }

  const maxVal = Math.max(...Object.values(counts), 1);
  const bars = [
    { label: "Positive", value: counts.Positive, color: "#4a9882", x: 110 },
    { label: "Neutral", value: counts.Neutral, color: "#6b8cc7", x: 300 },
    { label: "Negative", value: counts.Negative, color: "#c9787c", x: 490 },
  ];

  const baseline = 165;
  const maxHeight = 110;
  svg.innerHTML = `
    <line x1="50" y1="${baseline}" x2="650" y2="${baseline}" stroke="currentColor" opacity="0.15" stroke-width="1" />
    ${bars
      .map((bar) => {
        const h = (bar.value / maxVal) * maxHeight;
        const y = baseline - h;
        return `
          <rect x="${bar.x}" y="${y}" width="100" height="${h}" fill="${bar.color}" rx="8" opacity="0.85" />
          <text x="${bar.x + 50}" y="${baseline + 20}" text-anchor="middle" fill="currentColor" opacity="0.5" font-size="12" font-family="Inter, sans-serif">${bar.label}</text>
          <text x="${bar.x + 50}" y="${y - 8}" text-anchor="middle" fill="currentColor" font-size="13" font-weight="600" font-family="Inter, sans-serif">${bar.value}</text>
        `;
      })
      .join("")}
  `;
}

function enableFiltering() {
  const entriesWrap = document.getElementById("entries");
  const search = document.getElementById("entrySearch");
  const filter = document.getElementById("sentimentFilter");
  const emptyState = document.getElementById("emptyFilterState");
  if (!entriesWrap || !search || !filter || !emptyState) return;

  const cards = Array.from(entriesWrap.querySelectorAll(".entry"));
  const apply = () => {
    const query = search.value.trim().toLowerCase();
    const selected = filter.value;
    let visibleCount = 0;

    cards.forEach((card) => {
      const text = card.dataset.text || "";
      const sentiment = card.dataset.sentiment || "";
      const textMatch = text.includes(query);
      const sentimentMatch = selected === "All" || sentiment === selected;
      const visible = textMatch && sentimentMatch;
      card.classList.toggle("hidden", !visible);
      if (visible) visibleCount += 1;
    });

    emptyState.classList.toggle("hidden", visibleCount !== 0);
  };

  search.addEventListener("input", apply);
  filter.addEventListener("change", apply);
}

function initComposerUX() {
  const textarea = document.getElementById("entryText");
  const count = document.getElementById("charCount");
  const status = document.getElementById("draftStatus");
  const moodEstimate = document.getElementById("moodEstimate");
  const clearBtn = document.getElementById("clearDraftBtn");
  const form = document.getElementById("entryForm");
  const chips = document.querySelectorAll(".quick-chip");
  if (!textarea || !count || !status || !clearBtn || !form || !moodEstimate) return;

  const userId = document.body.dataset.userId || "guest";
  const key = `mind-mirror-draft:${userId}`;

  const update = () => {
    const len = textarea.value.length;
    count.textContent = `${len} characters`;
    moodEstimate.textContent = `Estimated mood: ${estimateMood(textarea.value)}`;
  };

  const saveDraft = () => {
    localStorage.setItem(key, textarea.value);
    status.textContent = "Draft saved";
  };

  const initial = localStorage.getItem(key);
  if (initial && !textarea.value.trim()) {
    textarea.value = initial;
    status.textContent = "Draft restored";
  }
  update();

  let timer = null;
  textarea.addEventListener("input", () => {
    update();
    status.textContent = "Saving...";
    clearTimeout(timer);
    timer = setTimeout(saveDraft, 250);
  });

  form.addEventListener("submit", () => {
    localStorage.removeItem(key);
    status.textContent = "Submitting...";
  });

  clearBtn.addEventListener("click", () => {
    textarea.value = "";
    update();
    localStorage.removeItem(key);
    status.textContent = "Draft cleared";
    textarea.focus();
  });

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.dataset.prompt || "";
      if (!textarea.value.trim()) {
        textarea.value = prompt;
      } else {
        textarea.value = `${textarea.value.trim()} ${prompt}`;
      }
      update();
      saveDraft();
      textarea.focus();
    });
  });
}

function estimateMood(text) {
  const t = (text || "").toLowerCase();
  if (!t.trim()) return "Neutral";

  const positiveWords = [
    "grateful", "happy", "good", "progress", "calm", "proud", "win", "better",
    "excited", "joyful", "peaceful", "love", "wonderful",
  ];
  const negativeWords = [
    "stressed", "anxious", "sad", "burnout", "tired", "angry", "overwhelmed",
    "worried", "frustrated", "lonely", "hopeless", "exhausted",
  ];

  let score = 0;
  for (const w of positiveWords) if (t.includes(w)) score += 1;
  for (const w of negativeWords) if (t.includes(w)) score -= 1;

  if (score >= 2) return "Positive";
  if (score <= -2) return "Negative";
  return "Neutral";
}

function animateKpis() {
  const counters = document.querySelectorAll(".stat-value");
  if (!counters.length) return;
  counters.forEach((el) => {
    const raw = el.textContent.trim();
    const numeric = Number.parseFloat(raw);
    if (Number.isNaN(numeric)) return;
    const suffix = raw.replace(String(numeric), "");
    const duration = 600;
    const start = performance.now();

    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = numeric * eased;
      el.textContent = `${Number.isInteger(numeric) ? Math.round(v) : v.toFixed(1)}${suffix}`;
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function drawProTrendFromDom() {
  const svg = document.getElementById("proTrendChart");
  if (!svg) return;
  const pointsSource = window.__proTrendPoints;
  if (!Array.isArray(pointsSource) || !pointsSource.length) return;

  const values = pointsSource.map((v) => Number(v) || 0);
  const width = 700;
  const height = 200;
  const padding = 24;
  const min = -1;
  const max = 1;
  const axisY = height - padding - ((0 - min) / (max - min)) * (height - padding * 2);
  const points = values.map((value, i) => {
    const x = padding + (i * (width - padding * 2)) / Math.max(1, values.length - 1);
    const y = height - padding - ((value - min) / (max - min)) * (height - padding * 2);
    return `${x},${y}`;
  });

  svg.innerHTML = `
    <line x1="${padding}" y1="${axisY}" x2="${width - padding}" y2="${axisY}" stroke="currentColor" opacity="0.15" stroke-width="1" stroke-dasharray="4,4"/>
    <polyline fill="none" stroke="#4a9882" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${points.join(" ")}"/>
    ${points.map((p) => {
      const [x, y] = p.split(",");
      return `<circle cx="${x}" cy="${y}" r="3.5" fill="#6b8cc7" stroke="#fff" stroke-width="1.5"/>`;
    }).join("")}
  `;
}

function initToasts() {
  const stack = document.getElementById("toastStack");
  if (!stack) return;
  setTimeout(() => {
    stack.querySelectorAll(".toast").forEach((toast) => {
      toast.style.transition = "opacity 260ms ease, transform 260ms ease";
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-8px)";
    });
    setTimeout(() => stack.remove(), 300);
  }, 3000);
}

function initDeleteModal() {
  const modal = document.getElementById("deleteModal");
  const preview = document.getElementById("deletePreview");
  const confirmBtn = document.getElementById("deleteConfirmBtn");
  const cancelBtn = document.getElementById("deleteCancelBtn");
  const triggers = document.querySelectorAll(".js-delete-trigger");
  if (!modal || !preview || !confirmBtn || !cancelBtn || !triggers.length) return;

  let pendingForm = null;

  const close = () => {
    modal.classList.add("hidden");
    pendingForm = null;
  };
  const openFor = (formEl, previewText) => {
    pendingForm = formEl;
    preview.textContent = previewText || "Selected journal entry";
    modal.classList.remove("hidden");
  };

  triggers.forEach((btn) => {
    btn.addEventListener("click", () => {
      const formEl = btn.closest("form");
      if (!formEl) return;
      openFor(formEl, btn.dataset.deletePreview);
    });
  });

  confirmBtn.addEventListener("click", () => {
    if (!pendingForm) return;
    confirmBtn.disabled = true;
    pendingForm.submit();
  });

  cancelBtn.addEventListener("click", close);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}

async function initDashboard() {
  initThemeToggle();
  initDeleteModal();
  initToasts();
  initComposerUX();
  animateKpis();
  try {
    const entries = await getEntries();
    drawTrend(entries);
    drawDistribution(entries);
    enableFiltering();
    drawProTrendFromDom();
  } catch (_err) {
    drawProTrendFromDom();
  }
}

initDashboard();
