import { readFileSync } from "node:fs";
import vm from "node:vm";

const [page, search, remembered] = process.argv.slice(2);
const html = readFileSync(page, "utf8");
const script = html.slice(html.indexOf("<script>") + "<script>".length,
                          html.lastIndexOf("</script>"));
const store = new Map(Object.entries(JSON.parse(remembered)));
const fetched = [];
let drawn = "";

const node = (id) => ({
  id, value: "", dataset: {},
  classList: { toggle() {}, contains: () => false },
  addEventListener() {}, querySelector: () => null, querySelectorAll: () => [],
  scrollIntoView() {}, insertAdjacentHTML() {}, append() {}, remove() {},
  get innerHTML() { return id === "app" ? drawn : ""; },
  set innerHTML(held) { if (id === "app") drawn = held; },
});
const app = node("app");

vm.runInContext(script, vm.createContext({
  document: {
    getElementById: (id) => id === "app" ? app
      : drawn.includes(`id="${id}"`) ? node(id) : null,
    body: node("body"),
    createElement: () => node(""),
  },
  localStorage: {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => { store.set(key, String(value)); },
    removeItem: (key) => { store.delete(key); },
  },
  location: { search, pathname: "/" },
  history: { replaceState() {} },
  fetch: async (url) => {
    fetched.push(url);
    return { ok: true, status: 200, text: async () => "[]" };
  },
  URLSearchParams, setTimeout,
}));

setTimeout(() => console.log(JSON.stringify(
  { drawn, remembered: Object.fromEntries(store), fetched })), 100);
