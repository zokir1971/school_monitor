<script>
  const ROLES = {{ responsible_roles|tojson }};
  const EXISTING = {{ member_roles|tojson }};

  function roleRowHtml(idx, roleVal="", ctxVal=""){
    const options = ROLES.map(r => {
      const sel = r.value === roleVal ? "selected" : "";
      return `<option value="${r.value}" ${sel}>${r.label_kz}</option>`;
    }).join("");

    return `
      <div class="role-row" data-idx="${idx}" style="display:grid;grid-template-columns:1fr 1fr auto;gap:10px;margin:10px 0">
        <div>
          <label>Роль</label>
          <select class="rr-role">
            <option value="">— выбери —</option>
            ${options}
          </select>
        </div>
        <div>
          <label>Контекст</label>
          <input class="rr-context" value="${ctxVal || ""}" placeholder="Напр: 1 смена / МО математики">
        </div>
        <div>
          <label>&nbsp;</label>
          <button type="button" onclick="removeRoleRow(${idx})">Удалить</button>
        </div>
      </div>
    `;
  }

  function addRoleRow(roleVal="", ctxVal=""){
    const box = document.getElementById("rolesBox");
    const idx = box.querySelectorAll(".role-row").length;
    box.insertAdjacentHTML("beforeend", roleRowHtml(idx, roleVal, ctxVal));
  }

  function removeRoleRow(idx){
    const row = document.querySelector(`.role-row[data-idx="${idx}"]`);
    if(row) row.remove();
    renumber();
  }

  function renumber(){
    const rows = Array.from(document.querySelectorAll("#rolesBox .role-row"));
    rows.forEach((row, i) => {
      row.dataset.idx = String(i);
      const btn = row.querySelector("button[type='button']");
      if(btn) btn.setAttribute("onclick", `removeRoleRow(${i})`);
    });
  }

  function buildHidden(){
    const hidden = document.getElementById("rolesHidden");
    hidden.innerHTML = "";
    const rows = Array.from(document.querySelectorAll("#rolesBox .role-row"));
    let j = 0;
    for(const row of rows){
      const role = (row.querySelector(".rr-role")?.value || "").trim();
      const ctx = (row.querySelector(".rr-context")?.value || "").trim();
      if(!role) continue;

      const a = document.createElement("input");
      a.type="hidden"; a.name=`roles[${j}].role`; a.value=role;
      hidden.appendChild(a);

      const b = document.createElement("input");
      b.type="hidden"; b.name=`roles[${j}].context`; b.value=ctx;
      hidden.appendChild(b);

      j++;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if(EXISTING && EXISTING.length){
      EXISTING.forEach(r => addRoleRow(r.role, r.context));
    } else {
      addRoleRow();
    }
    document.getElementById("rolesForm").addEventListener("submit", () => buildHidden());
  });
</script>