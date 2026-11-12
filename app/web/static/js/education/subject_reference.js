(() => {
  "use strict";
  const name = document.getElementById("subject-name-ru");
  const code = document.getElementById("subject-code");
  if (!name || !code) return;
  const transliteration = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"};
  function update() {
    const value = Array.from(name.value.trim().toLowerCase())
      .map(char => Object.hasOwn(transliteration, char) ? transliteration[char] : char)
      .join("").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    code.value = value;
    name.setCustomValidity(!value ? window.SchoolMonitorI18n.t("ed_268ddda7a6b3")
      : value.length > 100 ? window.SchoolMonitorI18n.t("ed_f0554022b23e") : "");
  }
  name.addEventListener("input", update);
  update();
})();
