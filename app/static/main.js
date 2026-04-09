// Frontend logic for:
// 1) Uploading a PDF
// 2) Triggering ingestion
// 3) Asking questions
// 4) Appending all Q/A pairs to the page
//

// Important:
// We are NOT doing backend conversation memory yet.
// We are only showing all messages on the page.

const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const ingestBtn = document.getElementById("ingestBtn");
const askBtn = document.getElementById("askBtn");
const questionInput = document.getElementById("questionInput");

const uploadStatus = document.getElementById("uploadStatus");
const ingestStatus = document.getElementById("ingestStatus");
const docStatus = document.getElementById("docStatus");
const chatContainer = document.getElementById("chatContainer");

async function refreshStatus() {
  try {
    const response = await fetch("/status");
    const data = await response.json();

    docStatus.innerHTML = `
      <p><strong>Uploaded file:</strong> ${data.uploaded_filename || "None"}</p>
      <p><strong>Ingested:</strong> ${data.ingested ? "Yes" : "No"}</p>
      <p><strong>Chunks count:</strong> ${data.chunks_count || 0}</p>
    `;
  } catch (error) {
    docStatus.innerHTML = `<p>Could not load status.</p>`;
  }
}

function addMessage(role, htmlContent) {
  const message = document.createElement("div");
  message.className = role === "user" ? "message user-message" : "message assistant-message";
  message.innerHTML = htmlContent;
  chatContainer.appendChild(message);

  // Auto-scroll to latest message
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function renderSources(sources) {
  if (!sources || sources.length === 0) {
    return `<div class="sources"><p><strong>Sources:</strong> No sources returned.</p></div>`;
  }

  const items = sources.map((src, index) => {
    return `
      <div class="source-card">
        <p><strong>Source ${index + 1}</strong></p>
        <p><strong>File:</strong> ${src.file ?? "unknown"}</p>
        <p><strong>Page:</strong> ${src.page ?? "unknown"}</p>
        <p><strong>Excerpt:</strong> ${src.excerpt ?? ""}</p>
      </div>
    `;
  }).join("");

  return `<div class="sources">${items}</div>`;
}

uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];

  if (!file) {
    uploadStatus.textContent = "Please choose a PDF file first.";
    return;
  }

  
  const formData = new FormData();
  formData.append("file", file);


  uploadStatus.textContent = "Uploading...";
  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      uploadStatus.textContent = data.detail || "Upload failed.";
      return;
    }

    uploadStatus.textContent = `Uploaded: ${data.filename}`;
    await refreshStatus();
  } catch (error) {
    uploadStatus.textContent = "Upload failed due to a network or server error.";
  }
});

ingestBtn.addEventListener("click", async () => {
  ingestStatus.textContent = "Ingesting... this can take time for large PDFs.";

  try {
    const response = await fetch("/ingest", {
      method: "POST",
    });

    const data = await response.json();

    if (!response.ok) {
      ingestStatus.textContent = data.detail || "Ingestion failed.";
      return;
    }

    ingestStatus.textContent = `Ingestion completed. Chunks: ${data.chunks_count}`;
    await refreshStatus();
  } catch (error) {
    ingestStatus.textContent = "Ingestion failed due to a network or server error.";
  }
});


askBtn.addEventListener("click", async () => {
  const question = questionInput.value.trim();

  if (!question) {
    return;
  }

  // Show user message first
  addMessage("user", `<p><strong>You:</strong> ${question}</p>`);

  // Clear the input box after sending
  questionInput.value = "";

  // Add a temporary assistant loading block
  const loadingMessage = document.createElement("div");
  loadingMessage.className = "message assistant-message";
  loadingMessage.innerHTML = `<p><strong>Assistant:</strong> Thinking...</p>`;
  chatContainer.appendChild(loadingMessage);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });

    const data = await response.json();

    // Remove temporary loading block
    loadingMessage.remove();

    if (!response.ok) {
      addMessage("assistant", `<p><strong>Assistant:</strong> ${data.detail || "Something went wrong."}</p>`);
      return;
    }

    const sourcesHtml = renderSources(data.sources);

    addMessage(
      "assistant",
      `
        <p><strong>Assistant:</strong></p>
        <div class="answer-text">${data.answer}</div>
        ${sourcesHtml}
      `
    );
  } catch (error) {
    loadingMessage.remove();
    addMessage("assistant", `<p><strong>Assistant:</strong> Request failed due to a network or server error.</p>`);
  }
});

// Load current status when the page opens
refreshStatus();
