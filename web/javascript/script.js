// ... previous constants
const Proceed = document.querySelector("#proceed");
const thumbnail = document.querySelector("#thumbnail_img");
const titleElem = document.querySelector(".title");
const authorElem = document.querySelector(".author");
const viewsElem = document.querySelector(".views");
const likesElem = document.querySelector(".likes");
const dislikesElem = document.querySelector(".dislikes");
const historyList = document.getElementById("history-list");

let _url = '';
let _title = '';

function setProceedLoading(isLoading) {
  Proceed.disabled = isLoading;
  Proceed.innerHTML = isLoading ? `<div class="loader-ring"></div>` : `Proceed`;
}

window.addEventListener("offline", () => toast("You are offline", "error"));

Proceed.addEventListener("click", async () => {
  const url = document.querySelector("#Url").value;
  if (!url) return toast("Please enter a URL", "info");

  setProceedLoading(true);

  try {
    const videoInfo = await eel.getVideo(url)();
    if (videoInfo.error) {
      toast(videoInfo.error, "error");
      return;
    }

    thumbnail.src = videoInfo.thumbnail;
    titleElem.innerText = videoInfo.title;
    authorElem.innerText = videoInfo.uploader;
    viewsElem.innerText = videoInfo.view_count + " views";
    likesElem.innerText = (videoInfo.like_count || 'N/A') + " likes";
    dislikesElem.innerText = (videoInfo.comment_count || 'N/A') + " comments";

    _url = url;
    _title = videoInfo.title;
    document.querySelector('.video').style.visibility = 'visible';
  } catch (err) {
    console.error("Error fetching video info:", err);
    toast("Error fetching video info", "error");
  } finally {
    setProceedLoading(false);
  }
});

async function download(resolution, ext, fromHistory = false, url = _url, title = _title) {
  const caller = event?.target;
  if (caller && caller.tagName === "BUTTON") {
    setButtonLoading(caller, true, "Starting...");
  }

  try {
    const response = await eel.downloadVideo(url, ext, resolution)();
    if (response.error) return toast(response.error, "error");

    createDownloadCard(response.id, title);
    if (!fromHistory) {
      saveToHistory(title, url, resolution, ext);
    }
    toast(`Started: ${title}`, "info");

  } catch (err) {
    console.error("Error starting download:", err);
    toast("Error downloading video", "error");

  } finally {
    if (caller && caller.tagName === "BUTTON") {
      setButtonLoading(caller, false);
    }
  }
}


function createDownloadCard(id, title) {
  const container = document.getElementById("download-cards");
  const card = document.createElement("div");
  card.className = "download-card";
  card.dataset.id = id;
  card.innerHTML = `
    <div class="card-header">${title}</div>
    <div class="progress-wrapper">
      <div class="progress-bar">0%</div>
    </div>
    <div class="progress-info">
      <span class="progress-speed">Speed: --</span> |
      <span class="progress-eta">ETA: --</span> |
      <span class="progress-size">Size: --</span> |
      <span class="progress-ext">Format: --</span>
    </div>
  `;
  container.appendChild(card);
}

function toast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toast-container");
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `
    <span>${message}</span>
    <button class="close-btn">&times;</button>
  `;

  container.appendChild(t);
  setTimeout(() => t.classList.add("visible"), 100);

  const autoRemove = setTimeout(() => {
    t.classList.remove("visible");
    setTimeout(() => container.removeChild(t), 300);
  }, duration);

  t.querySelector(".close-btn").addEventListener("click", () => {
    clearTimeout(autoRemove);
    t.classList.remove("visible");
    setTimeout(() => container.removeChild(t), 300);
  });
}

function setButtonLoading(button, isLoading, loadingText = "") {
  if (isLoading) {
    button.disabled = true;
    button.dataset.originalText = button.innerHTML;
    button.innerHTML = `
      <div class="loader-ring small-loader"></div>
      ${loadingText}
    `;
  } else {
    button.disabled = false;
    if (button.dataset.originalText) {
      button.innerHTML = button.dataset.originalText;
      delete button.dataset.originalText;
    }
  }
}

function scheduleCardRemoval(card) {
  setTimeout(() => {
    card.classList.add("fade-out");
    setTimeout(() => card.remove(), 1000);
  }, 90000);
}

function stripAnsi(str) {
  const ansiRegex = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;
  return str.replace(ansiRegex, '');
}

function updateProgress(id, d) {
  const card = document.querySelector(`.download-card[data-id="${id}"]`);
  if (!card) return;

  const bar = card.querySelector(".progress-bar");
  const speedElem = card.querySelector(".progress-speed");
  const etaElem = card.querySelector(".progress-eta");
  const sizeElem = card.querySelector(".progress-size");
  const extElem = card.querySelector(".progress-ext");

  if (d.status === 'finished') {
    bar.style.width = "100%";
    bar.innerText = "Completed";
    speedElem.innerText = "Speed: —";
    etaElem.innerText = "ETA: —";
    sizeElem.innerText = "Size: —";
    extElem.innerText = "Format: —";
    toast("Download completed", "success");
    scheduleCardRemoval(card);

  } else if (d.status === 'error') {
    bar.style.backgroundColor = "red";
    bar.innerText = "Error";
    toast(`Error: ${d.message}`, "error");
    scheduleCardRemoval(card);

  } else {
    const raw = stripAnsi(d._default_template || '');
    const match = raw.match(/(\d{1,3}(?:\.\d+)?)%/);
    const speed = d.speed ? `${(d.speed / 1024).toFixed(2)} KB/s` : '--';
    const eta = d.eta ? `${d.eta}s` : '--';
    const totalBytes = d.total_bytes || d.total_bytes_estimate || 0;
    const size = totalBytes ? `${(totalBytes / 1024 / 1024).toFixed(2)} MB` : '--';
    const ext = d.ext || '--';

    if (match) {
      const pct = parseFloat(match[1]);
      bar.style.width = `${pct}%`;
      bar.innerText = `${pct.toFixed(1)}%`;
    }

    speedElem.innerText = `Speed: ${speed}`;
    etaElem.innerText = `ETA: ${eta}`;
    sizeElem.innerText = `Size: ${size}`;
    extElem.innerText = `Format: ${ext}`;
  }
}

eel.expose(updateProgress);

function saveToHistory(title, url, resolution, ext) {
  const history = JSON.parse(localStorage.getItem("downloadHistory")) || [];
  const entry = {
    title,
    url,
    resolution,
    ext,
    date: new Date().toLocaleString(),
  };
  history.unshift(entry);
  localStorage.setItem("downloadHistory", JSON.stringify(history));
}

function loadHistory() {
  historyList.innerHTML = "";
  const history = JSON.parse(localStorage.getItem("downloadHistory")) || [];
  if (history.length === 0) {
    historyList.innerHTML = "<p>No download history found.</p>";
    return;
  }

  history.forEach((item) => {
    const div = document.createElement("div");
    div.className = "history-item";
    div.innerHTML = `
      <span>${item.title}</span>
      <span>${item.date}</span>
      <button class="history-download"
        data-url="${item.url}"
        data-ext="${item.ext}"
        data-resolution="${item.resolution}"
        data-title="${item.title}">
        Download Again
      </button>
    `;
    historyList.appendChild(div);
  });
}

// Wrap modal events in DOMContentLoaded to ensure elements exist

document.addEventListener("DOMContentLoaded", () => {
  const historyBtn = document.getElementById("history-btn");
  const historyModal = document.getElementById("history-modal");
  const closeHistory = document.getElementById("close-history");
  const clearHistory = document.getElementById("clear-history");

  if (historyBtn && historyModal && closeHistory) {
    historyBtn.addEventListener("click", () => {
      loadHistory();
      historyModal.classList.remove("hidden");
    });

    closeHistory.addEventListener("click", () => {
      historyModal.classList.add("hidden");
    });
  }

  if (clearHistory) {
    clearHistory.addEventListener("click", () => {
      if (confirm("Are you sure you want to clear your download history?")) {
        localStorage.removeItem("downloadHistory");
        loadHistory();
        toast("History cleared", "info");
      }
    });
  }
});

// Re-download from history

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("history-download")) {
    const url = e.target.dataset.url;
    const ext = e.target.dataset.ext;
    const resolution = e.target.dataset.resolution;
    const title = e.target.dataset.title;
    download(resolution, ext, true, url, title);
  }
});

document.getElementById('paste').addEventListener('click', async function () {
  try {
    const text = await navigator.clipboard.readText();

    const urlPattern = /^(https?:\/\/)[\w.-]+\.[a-z]{2,}(\/\S*)?$/i;

    if (!urlPattern.test(text.trim())) {
      toast("Clipboard does not contain a valid URL", "error");
      return;
    }

    document.getElementById('Url').value = text.trim();
    toast("URL pasted from clipboard", "success");

  } catch (err) {
    console.error("Failed to read clipboard contents:", err);
    toast("Clipboard access failed", "error");
  }
});

document.getElementById('Url').addEventListener("drop", e => {
  e.preventDefault();
  document.getElementById('Url').value = e.dataTransfer.getData("text");
});