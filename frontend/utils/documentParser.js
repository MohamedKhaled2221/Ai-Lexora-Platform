import * as pdfjsLib from "pdfjs-dist";
import mammoth from "mammoth/mammoth.browser";
import { createWorker } from "tesseract.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.mjs", import.meta.url).toString();

const MAX_FILE_SIZE = 25 * 1024 * 1024;
const supportedExtensions = new Set(["txt", "md", "csv", "json", "pdf", "doc", "docx", "png", "jpg", "jpeg", "webp"]);

function getExtension(fileName) {
  return fileName.split(".").pop()?.toLowerCase() || "";
}

function normalizeText(value) {
  return String(value || "").replace(/\u0000/g, "").replace(/\s+/g, " ").trim();
}

function parseStructuredText(text, extension) {
  if (extension !== "json") return text;

  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    throw new Error("ملف JSON غير صالح.");
  }
}

async function parsePdfFile(file) {
  const data = new Uint8Array(await file.arrayBuffer());
  const pdf = await pdfjsLib.getDocument({ data }).promise;
  const pages = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    pages.push({ page: pageNumber, text: normalizeText(content.items.map((item) => item.str).join(" ")) });
  }

  return { text: pages.map((item) => item.text).filter(Boolean).join("\n"), pages };
}

async function parseDocxFile(file) {
  const result = await mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() });
  return { text: normalizeText(result.value), pages: [] };
}

async function parseImageFile(file) {
  const worker = await createWorker("eng+ara");
  try {
    const result = await worker.recognize(file);
    return { text: normalizeText(result.data.text), pages: [] };
  } finally {
    await worker.terminate();
  }
}

export function validateDocumentFile(file) {
  const extension = getExtension(file.name);
  const mimeIsAllowed = !file.type || [
    "text/plain", "text/markdown", "text/csv", "application/json", "application/pdf",
    "image/png", "image/jpeg", "image/webp",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ].includes(file.type);

  if (!supportedExtensions.has(extension) || !mimeIsAllowed) {
    throw new Error("نوع الملف غير مدعوم. الأنواع المدعومة هي PDF وWord وTXT وMD وCSV وJSON.");
  }
  if (!file.size) throw new Error("الملف فارغ ولا يحتوي على محتوى قابل للبحث.");
  if (file.size > MAX_FILE_SIZE) throw new Error("حجم الملف يتجاوز الحد المسموح وهو 25 ميجابايت.");
  if (extension === "doc") throw new Error("ملفات DOC القديمة غير مدعومة للقراءة الموثوقة داخل المتصفح. استخدم DOCX أو PDF.");

  return extension;
}

export async function parseDocumentFile(file) {
  const extension = validateDocumentFile(file);
  let parsed;

  if (extension === "pdf") parsed = await parsePdfFile(file);
  else if (extension === "docx") parsed = await parseDocxFile(file);
  else if (["png", "jpg", "jpeg", "webp"].includes(extension)) parsed = await parseImageFile(file);
  else parsed = { text: parseStructuredText(await file.text(), extension), pages: [] };

  const text = normalizeText(parsed.text);
  if (!text) throw new Error("تعذر استخراج نص من الملف.");

  return { fileName: file.name, extension, text, pages: parsed.pages };
}