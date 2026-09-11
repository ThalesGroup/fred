declare global {
  interface Window {
    __attack(message: unknown): void;
  }
}

const targetOrigin = new URLSearchParams(window.location.search).get(
  "targetOrigin",
);
if (!targetOrigin) throw new Error("targetOrigin is required");

window.__attack = (message: unknown) => {
  window.parent.frames[0]?.postMessage(message, targetOrigin);
  window.parent.postMessage(message, "*");
};
export {};
