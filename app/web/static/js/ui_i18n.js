/* Extend the server-provided catalog with explicit UI keys as modules migrate. */
(() => {
  "use strict";
  const element = document.getElementById("ui-i18n");
  if (!element) return;
  const data = JSON.parse(element.textContent);
  window.SchoolMonitorI18n = Object.freeze({
    language: data.language,
    t: (key, values = {}) => {
      const text = Object.prototype.hasOwnProperty.call(data.messages, key) ? data.messages[key] : key;
      return text.replace(/\{(p\d+)\}/g, (match, name) =>
        Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match);
    }
  });
})();
