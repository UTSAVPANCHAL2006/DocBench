import raw from "@/data/showcase.json";

// Shapes of data/showcase.json, written by showcase/build.py from the latest benchmark run.
export type Pipeline = "ocr_regex" | "ocr_reference" | "ocr_text_llm" | "vision_llm" | "vision_verified";
export type Style = "pad" | "emr" | "invoice" | "claim";
export type Shown = "ocr_reference" | "ocr_text_llm" | "vision_verified";

export interface Headline {
  pipeline: Pipeline;
  field_acc: number;
  critical_acc: number;
  critical_wrong: number;
  critical_silent: number;
  critical_caught: number;
  flags: number;
  false_alarms: number;
  docs_flagged: number;
  hallucinated: number;
  p50_ms: number;
  cost_per_1k: number;
  docs: number;
}

export interface Cell { v: string; ok: boolean; cat: string | null; flag: boolean }
export interface Row { field: string; label: string; gt: string; critical: boolean; cells: Record<Shown, Cell | null> }
export interface Check {
  rule: string; ok: boolean; detail: string; where: string;
  read: Record<string, string>; truth: Record<string, string>; real: boolean;
}
export interface Page { img: string; w: number; h: number }
export interface QueueItem extends Check { doc: string; style: Style; degradation: string }
export interface Specimen {
  id: string; style: Style; degradation: string; note: string;
  img: string; w: number; h: number; acc: Record<Shown, number>; rows: Row[];
  trace: { ocr: string; model: string; checks: Check[] };
}

export interface Showcase {
  run: { timestamp: string; model: string | null; effort: string | null };
  docs: number;
  headline: Headline[];
  degradations: string[];
  by_degradation: Record<Pipeline, number[]>;
  styles: Style[];
  by_style: Record<Pipeline, number[]>;
  specimens: Specimen[];
  queue: QueueItem[];
  pages: Record<string, Page>;
}

export const data = raw as unknown as Showcase;
export const byPipeline = Object.fromEntries(data.headline.map(h => [h.pipeline, h])) as Record<Pipeline, Headline>;
export const runDate = data.run.timestamp.replace(" (rescored)", "").split(" ")[0];

export const NAMES: Record<Pipeline, [string, string]> = {
  ocr_regex: ["OCR", "Tesseract + regex"],
  ocr_reference: ["OCR + reference", "Repair with drug list, DINs, sig words"],
  ocr_text_llm: ["OCR text → LLM", "Model sees OCR text, not the page"],
  vision_llm: ["Vision LLM", "Model sees the page image"],
  vision_verified: ["Vision + validation", "Vision, then rule checks flag errors"],
};
export const STYLE: Record<Style, string> = { pad: "Handwritten Rx", emr: "EMR Rx", invoice: "Invoice", claim: "Claim" };
export const DEG: Record<string, string> = {
  clean: "clean", skew: "skewed", blur: "blurred", noise: "speckled", fax: "faxed", low_res: "75 dpi",
};

export const REPO = "https://github.com/UTSAVPANCHAL2006/DocBench";

export const f1 = (n: number) => n.toFixed(1);
export const asset = (path: string) => `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/${path}`;
