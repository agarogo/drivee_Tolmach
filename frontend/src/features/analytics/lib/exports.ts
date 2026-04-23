import type { QueryResultRow } from "../../../shared/types";

function csvValue(value: unknown) {
  return JSON.stringify(value ?? "");
}

export function exportRowsToCsv(
  rows: QueryResultRow[],
  fileName = "tolmach-result-snapshot.csv",
) {
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const csv = [
    columns.join(","),
    ...rows.map((row) => columns.map((column) => csvValue(row[column])).join(",")),
  ].join("\n");

  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

async function captureNode(node: HTMLElement) {
  const { default: html2canvas } = await import("html2canvas");
  return html2canvas(node, {
    backgroundColor: "#161a1c",
    scale: Math.max(window.devicePixelRatio, 2),
    useCORS: true,
  });
}

export async function exportNodeToPng(node: HTMLElement, fileName = "tolmach-result.png") {
  const canvas = await captureNode(node);
  const link = document.createElement("a");
  link.href = canvas.toDataURL("image/png");
  link.download = fileName;
  link.click();
}

export async function exportNodeToPdf(node: HTMLElement, fileName = "tolmach-result.pdf") {
  const canvas = await captureNode(node);
  const { jsPDF } = await import("jspdf");

  const pdf = new jsPDF("p", "mm", "a4");
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const imageWidth = pageWidth;
  const imageHeight = (canvas.height * imageWidth) / canvas.width;
  const imageData = canvas.toDataURL("image/png");

  let remainingHeight = imageHeight;
  let positionY = 0;
  pdf.addImage(imageData, "PNG", 0, positionY, imageWidth, imageHeight);
  remainingHeight -= pageHeight;

  while (remainingHeight > 0) {
    positionY = remainingHeight - imageHeight;
    pdf.addPage();
    pdf.addImage(imageData, "PNG", 0, positionY, imageWidth, imageHeight);
    remainingHeight -= pageHeight;
  }

  pdf.save(fileName);
}
