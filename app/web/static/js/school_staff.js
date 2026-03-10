  // responsible_roles из бэка
const RESPONSIBLE_ROLES = [
  {% for r in responsible_roles %}
    { value: "{{ r.value }}", label: "{{ (r.label_ru or r.label_kz or r.value) | e }}" },
  {% endfor %}
];

function roleOptionsHtml(selected) {
  return RESPONSIBLE_ROLES.map(r => {
    const sel = (selected && selected === r.value) ? "selected" : "";
    return `<option value="${r.value}" ${sel}>${r.label}</option>`;
  }).join("");
}

function addRoleRow(value="", ctx="") {
  const box = document.getElementById("rolesBox");
  const idx = box.children.length;

  const wrap = document.createElement("div");
  wrap.className = "role-item";
  wrap.innerHTML = `
    <select name="roles[${idx}][role]" required>
      <option value="" disabled ${value ? "" : "selected"}>Выберите роль…</option>
      ${roleOptionsHtml(value)}
    </select>
    <input name="roles[${idx}][ctx]" placeholder="Контекст (необязательно)" value="${ctx.replaceAll('"','&quot;')}">
    <button class="remove" type="button" title="Удалить" onclick="this.parentElement.remove(); reindexRoles();">✕</button>
  `;
  box.appendChild(wrap);
}

function reindexRoles(){
  const box = document.getElementById("rolesBox");
  Array.from(box.children).forEach((row, i) => {
    const sel = row.querySelector("select");
    const inp = row.querySelector("input");
    sel.name = `roles[${i}][role]`;
    inp.name = `roles[${i}][ctx]`;
  });
}

// по умолчанию 1 строка роли
addRoleRow();

// добавления сотрудника
document.addEventListener("DOMContentLoaded", () => {
  const sel = document.getElementById("positionSelect");
  const other = document.getElementById("positionOther");

  function sync(){
    const isOther = sel.value === "__other__";
    other.style.display = isOther ? "block" : "none";
    if (isOther) other.required = true;
    else other.required = false;
  }

  sel.addEventListener("change", sync);
  sync();
});
