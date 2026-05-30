const pdfInput = document.querySelector("#pdfInput");
const fileLabel = document.querySelector("#fileLabel");
const goalInput = document.querySelector("#goalInput");
const difficultyInput = document.querySelector("#difficultyInput");
const countInput = document.querySelector("#countInput");
const generateButton = document.querySelector("#generateButton");
const statusLine = document.querySelector("#statusLine");
const quizOutput = document.querySelector("#quizOutput");
const traceOutput = document.querySelector("#traceOutput");

let currentDocumentId = null;
let currentTrace = [];

pdfInput.addEventListener("change", async () => {
  const file = pdfInput.files?.[0];
  if (!file) return;
  fileLabel.textContent = file.name;
  await uploadPdf(file);
});

generateButton.addEventListener("click", async () => {
  if (!currentDocumentId) {
    statusLine.textContent = "Upload a PDF before generating a quiz.";
    return;
  }
  await generateQuiz();
});

async function uploadPdf(file) {
  setBusy(true, "Uploading and indexing PDF...");
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/documents", { method: "POST", body: form });
    const payload = await readJson(response);
    currentDocumentId = payload.document_id;
    currentTrace = payload.trace;
    renderTrace(currentTrace);
    statusLine.textContent = `Indexed ${payload.page_count} pages into ${payload.chunk_count} chunks.`;
  } catch (error) {
    statusLine.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function generateQuiz() {
  setBusy(true, "Retrieving chunks and asking Gemma...");
  try {
    const response = await fetch("/api/quizzes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_id: currentDocumentId,
        quiz_goal: goalInput.value,
        difficulty: difficultyInput.value,
        question_count: Number(countInput.value),
      }),
    });
    const payload = await readJson(response);
    renderQuiz(payload.quiz);
    renderRetrieved(payload.retrieved);
    currentTrace = [...currentTrace, ...payload.trace];
    renderTrace(currentTrace);
    statusLine.textContent = "Quiz generated from retrieved document evidence.";
  } catch (error) {
    statusLine.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function renderQuiz(quiz) {
  const questions = quiz.questions || [];
  quizOutput.innerHTML = `
    <h2>${escapeHtml(quiz.title || "Generated Quiz")}</h2>
    ${questions
      .map(
        (item, index) => `
        <article class="question">
          <h3>${index + 1}. ${escapeHtml(item.question || "")}</h3>
          <ol type="A">
            ${(item.options || []).map((option) => `<li>${escapeHtml(option)}</li>`).join("")}
          </ol>
          <p class="answer">Answer: ${escapeHtml(item.answer || "")}</p>
          <p>${escapeHtml(item.explanation || "")}</p>
          <small>Source: ${escapeHtml(item.source_chunk_id || "not provided")}</small>
        </article>
      `,
      )
      .join("")}
  `;
}

function renderRetrieved(retrieved) {
  currentTrace.push({
    stage: "evidence",
    status: "ok",
    detail: "Top chunks selected for generation.",
    metrics: { chunks: retrieved },
  });
}

function renderTrace(trace) {
  traceOutput.innerHTML = trace
    .map(
      (item) => `
      <section class="trace-item">
        <div class="trace-head">
          <span>${escapeHtml(item.stage)}</span>
          <span>${escapeHtml(item.status)}</span>
        </div>
        <p>${escapeHtml(item.detail)}</p>
        <pre>${escapeHtml(JSON.stringify(item.metrics || {}, null, 2))}</pre>
      </section>
    `,
    )
    .join("");
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

function setBusy(isBusy, message) {
  generateButton.disabled = isBusy;
  if (message) statusLine.textContent = message;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
