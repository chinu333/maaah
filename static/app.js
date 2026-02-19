/* ================================================================
   MAAAH – Two-Panel UI  ·  Auto-Orchestration + Streaming
   ================================================================ */

(function () {
  "use strict";

  // ── DOM refs ──────────────────────────────────────────────────
  const messageInput   = document.getElementById("messageInput");
  const sendBtn        = document.getElementById("sendBtn");
  const fileInput      = document.getElementById("fileInput");
  const attachBtn      = document.getElementById("attachBtn");
  const uploadStatus   = document.getElementById("uploadStatus");
  const fileChip       = document.getElementById("fileChip");
  const fileChipName   = document.getElementById("fileChipName");
  const fileChipRemove = document.getElementById("fileChipRemove");
  const activeLabel    = document.getElementById("activeAgentLabel");
  // Error toast removed – errors display inline in response cards
  const responseScroll = document.getElementById("responseScroll");
  const responseList   = document.getElementById("responseList");
  const welcomeState   = document.getElementById("welcomeState");
  const clearBtn       = document.getElementById("clearBtn");
  const agentPills     = document.querySelectorAll(".agent-pill");
  const panelDivider   = document.getElementById("panelDivider");
  const panelInput     = document.querySelector(".panel-input");

  // ── State ─────────────────────────────────────────────────────
  let uploadedFilePath = null;
  let isSending        = false;

  // Stable session ID per browser tab (persists across messages)
  const SESSION_ID = "web-" + Math.random().toString(36).slice(2, 10) + "-" + Date.now();

  // ── Marked.js config ──────────────────────────────────────────
  marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function (code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return hljs.highlightAuto(code).value;
    },
  });

  // ── Agent pills are display-only (no manual selection) ────────
  //    They light up when the backend reports which agents were called.

  // ── File attach (clip icon) ───────────────────────────────────
  attachBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    uploadStatus.textContent = "Uploading…";
    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      uploadedFilePath = data.saved_path;
      uploadStatus.textContent = "";
      fileChipName.textContent = data.filename;
      fileChip.hidden = false;
    } catch (err) {
      showError("Upload failed: " + err.message);
      uploadStatus.textContent = "";
    }
    fileInput.value = "";
  });

  // Remove file chip
  fileChipRemove.addEventListener("click", () => {
    uploadedFilePath = null;
    fileChip.hidden = true;
    fileChipName.textContent = "";
  });

  // ── Keyboard: Enter to send, Shift+Enter for newline ──────────
  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener("click", () => sendMessage());

  // ── Clear responses ───────────────────────────────────────────
  clearBtn.addEventListener("click", () => {
    responseList.innerHTML = "";
    clearAgentHighlights();
    if (welcomeState) welcomeState.style.display = "flex";
  });

  // ── Error handling (inline in response cards) ────────────────
  function showError(msg) {
    console.warn("MAAAH error:", msg);
  }

  // ── Panel resizer ─────────────────────────────────────────────
  let isResizing = false;
  panelDivider.addEventListener("mousedown", (e) => {
    isResizing = true;
    panelDivider.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!isResizing) return;
    const mainRect = document.querySelector(".app-main").getBoundingClientRect();
    const pct = ((e.clientX - mainRect.left) / mainRect.width) * 100;
    if (pct > 25 && pct < 75) {
      panelInput.style.width = pct + "%";
    }
  });
  document.addEventListener("mouseup", () => {
    if (isResizing) {
      isResizing = false;
      panelDivider.classList.remove("dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
  });

  // ================================================================
  // AGENT HIGHLIGHT HELPERS
  // ================================================================
  function clearAgentHighlights() {
    agentPills.forEach((p) => p.classList.remove("called"));
    activeLabel.textContent = "Auto";
  }

  function highlightAgents(agents) {
    agentPills.forEach((p) => {
      p.classList.remove("called");
      if (agents.includes(p.dataset.agent)) {
        p.classList.add("called");
      }
    });
    // Update the label in the compose bar
    activeLabel.textContent = agents.map(capitalize).join(" · ");
  }

  // ================================================================
  // SEND MESSAGE
  // ================================================================
  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || isSending) return;

    isSending = true;
    sendBtn.disabled = true;
    // (error toast removed)

    // Hide welcome
    if (welcomeState) welcomeState.style.display = "none";

    // Reset agent highlights (they'll update on response)
    clearAgentHighlights();

    // Build response card (badges added after response)
    const card = createResponseCard(text);
    responseList.appendChild(card);
    scrollToBottom();

    messageInput.value = "";

    // Show loading
    const bodyEl = card.querySelector(".rc-body");
    bodyEl.innerHTML = '<div class="loading-bar"><span></span><span></span><span></span></div>';

    try {
      const payload = {
        message: text,
        session_id: SESSION_ID,
      };
      if (uploadedFilePath) payload.file_path = uploadedFilePath;

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || res.statusText);
      }

      const data = await res.json();

      // Determine which agents were called
      const agentsCalled = data.agents_called || [data.agent];

      // Highlight agent pills
      highlightAgents(agentsCalled);

      // Add badges to response card header
      updateCardBadges(card, agentsCalled);

      // Clear loading, do streaming render
      bodyEl.innerHTML = "";
      await streamRender(bodyEl, data.reply);

    } catch (err) {
      bodyEl.innerHTML = "";
      showError(err.message);
      bodyEl.innerHTML = '<p style="color:var(--red);">⚠ ' + escapeHtml(err.message) + '</p>';
    } finally {
      isSending = false;
      sendBtn.disabled = false;
      messageInput.focus();
    }
  }

  // ================================================================
  // CREATE RESPONSE CARD  (badges added post-response via updateCardBadges)
  // ================================================================
  function createResponseCard(query) {
    const card = document.createElement("div");
    card.className = "response-card";

    const header = document.createElement("div");
    header.className = "rc-header";

    const avatar = document.createElement("div");
    avatar.className = "rc-avatar user-avatar";
    avatar.textContent = "U";

    const queryEl = document.createElement("div");
    queryEl.className = "rc-query";
    queryEl.textContent = query;

    const badges = document.createElement("div");
    badges.className = "rc-badges";

    header.appendChild(avatar);
    header.appendChild(queryEl);
    header.appendChild(badges);

    const body = document.createElement("div");
    body.className = "rc-body";

    card.appendChild(header);
    card.appendChild(body);
    return card;
  }

  function updateCardBadges(card, agents) {
    const container = card.querySelector(".rc-badges");
    container.innerHTML = "";
    agents.forEach((agent) => {
      const badge = document.createElement("span");
      badge.className = "rc-agent-badge";
      badge.setAttribute("data-agent", agent);
      badge.textContent = agent;
      container.appendChild(badge);
    });
  }

  // ================================================================
  // STREAMING TEXT RENDER  (character-by-character with dynamic color)
  // ================================================================
  async function streamRender(container, fullText) {
    // Parse markdown first to get the final HTML
    const parsedHTML = marked.parse(fullText);

    // If the response contains images (e.g. chart PNGs), skip streaming
    // and render directly so images display properly
    if (/!\[.*?\]\(.*?\)/.test(fullText)) {
      container.innerHTML = parsedHTML;
      enhanceCodeBlocks(container);
      startColorCycle(container);
      scrollToBottom();
      return;
    }

    // We'll stream the raw text char-by-char with color, then snap to full markdown
    const plainText = fullText;
    const streamEl = document.createElement("div");
    streamEl.classList.add("streaming-cursor");
    container.appendChild(streamEl);

    const charDelay = Math.max(4, Math.min(18, 2000 / plainText.length));
    let i = 0;

    await new Promise((resolve) => {
      function tick() {
        // Batch a few characters per frame for large texts
        const batch = Math.max(1, Math.ceil(plainText.length / 400));
        for (let b = 0; b < batch && i < plainText.length; b++, i++) {
          const ch = plainText[i];
          if (ch === "\n") {
            streamEl.appendChild(document.createElement("br"));
          } else {
            const span = document.createElement("span");
            span.className = "stream-char";
            span.textContent = ch;
            // Stagger the animation start slightly for a wave effect
            span.style.animationDelay = (i * 8) % 600 + "ms";
            streamEl.appendChild(span);
          }
        }
        scrollToBottom();
        if (i < plainText.length) {
          setTimeout(tick, charDelay);
        } else {
          resolve();
        }
      }
      tick();
    });

    // Remove cursor
    streamEl.classList.remove("streaming-cursor");

    // Snap to properly rendered markdown with code highlighting
    await sleep(200);
    container.innerHTML = parsedHTML;
    enhanceCodeBlocks(container);
    startColorCycle(container);
    scrollToBottom();
  }

  // ================================================================
  // CODE BLOCK ENHANCEMENT
  // ================================================================
  function enhanceCodeBlocks(container) {
    container.querySelectorAll("pre code").forEach((block) => {
      // Detect language
      const classes = block.className || "";
      const langMatch = classes.match(/language-(\w+)/);
      const lang = langMatch ? langMatch[1] : "code";

      // Create header
      const header = document.createElement("div");
      header.className = "code-header";

      const langLabel = document.createElement("span");
      langLabel.textContent = lang;

      const copyBtn = document.createElement("button");
      copyBtn.className = "copy-code-btn";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(block.textContent).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
        });
      });

      header.appendChild(langLabel);
      header.appendChild(copyBtn);

      // Insert header before <code> inside <pre>
      const pre = block.parentElement;
      pre.insertBefore(header, pre.firstChild);

      // Highlight
      hljs.highlightElement(block);
    });
  }

  // ── Utilities ─────────────────────────────────────────────────
  function startColorCycle(container) {
    const skip = new Set(["PRE", "CODE", "A", "BUTTON", "SVG", "IMG"]);
    let charIndex = 0;

    function wrapTextNodes(node) {
      if (skip.has(node.nodeName)) return;
      if (node.closest && (node.closest("pre") || node.closest("code") || node.closest("a"))) return;

      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent;
        if (!text.trim()) return;
        const frag = document.createDocumentFragment();
        for (const ch of text) {
          if (ch === " " || ch === "\n") {
            frag.appendChild(document.createTextNode(ch));
          } else {
            const span = document.createElement("span");
            span.className = "rendered-char";
            span.textContent = ch;
            span.style.animationDelay = (charIndex * 30 % 4000) + "ms";
            charIndex++;
            frag.appendChild(span);
          }
        }
        node.parentNode.replaceChild(frag, node);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        Array.from(node.childNodes).forEach(wrapTextNodes);
      }
    }

    wrapTextNodes(container);
  }

  function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  function escapeHtml(str) {
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
  }
  function scrollToBottom() {
    responseScroll.scrollTop = responseScroll.scrollHeight;
  }
  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
})();
