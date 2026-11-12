// Reading and writing form fields from outside React (voice fill, smart paste). Values are
// set through the native setter and announced with input/change events, so both
// uncontrolled fields and controlled ones (value + onChange) pick them up.

export type FillableField = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

const TEXT_TYPES = new Set(["text", "email", "tel", "number", "url", "search", "checkbox", ""]);

/** Fields voice can fill, in on-screen order. Passwords, dates and files are skipped. */
export function fillableFields(form: HTMLFormElement): FillableField[] {
  return Array.from(form.elements).filter((el): el is FillableField => {
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) return false;
    if (el.disabled || el.dataset.voice === "off") return false;
    if (el instanceof HTMLInputElement && (!TEXT_TYPES.has(el.type) || el.readOnly)) return false;
    if (el instanceof HTMLTextAreaElement && el.readOnly) return false;
    return el.getClientRects().length > 0; // visible
  });
}

export function fieldLabel(el: FillableField): string {
  const label = el.labels?.[0];
  const text = label?.querySelector("span")?.textContent ?? label?.textContent;
  return (text || el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || "this field").trim();
}

export function fieldValue(el: FillableField): string | boolean {
  return el instanceof HTMLInputElement && el.type === "checkbox" ? el.checked : el.value;
}

export function setFieldValue(el: FillableField, value: string | boolean) {
  if (el instanceof HTMLInputElement && el.type === "checkbox") {
    if (el.checked !== Boolean(value)) el.click(); // fires React's onChange
    return;
  }
  const proto = Object.getPrototypeOf(el) as object;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, String(value));
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/** Briefly highlight fields that were filled for the user. */
export function flash(el: Element) {
  el.setAttribute("data-autofilled", "");
  window.setTimeout(() => el.removeAttribute("data-autofilled"), 2500);
}
