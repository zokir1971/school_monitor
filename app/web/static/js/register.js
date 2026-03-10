// Селектор выбора регион-район-школа
document.addEventListener("DOMContentLoaded", () => {
  const regionSelect = document.getElementById("regionSelect");
  const districtSelect = document.getElementById("districtSelect");
  const schoolSelect = document.getElementById("schoolSelect");

  // Если на странице нет этих селекторов — просто выходим
  if (!regionSelect || !districtSelect || !schoolSelect) return;

  function resetSelect(sel, placeholder) {
    sel.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholder;
    sel.appendChild(opt);
    sel.value = "";
  }

  async function fetchJSON(url) {
    const r = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  }

  // ---------------------------------------------------
  // 1) При загрузке страницы подгружаем список областей
  // ---------------------------------------------------
  (async () => {
    resetSelect(regionSelect, "— выберите область —");
    resetSelect(districtSelect, "— сначала выберите область —");
    resetSelect(schoolSelect, "— сначала выберите район —");
    districtSelect.disabled = true;
    schoolSelect.disabled = true;

    try {
      const regions = await fetchJSON("/api/org/regions");
      for (const r of regions) {
        const opt = document.createElement("option");
        opt.value = r.id;
        opt.textContent = r.name;
        regionSelect.appendChild(opt);
      }
    } catch (e) {
      console.error("Не удалось загрузить области:", e);
    }
  })();

  // ---------------------------------------------------
  // 2) При выборе области подгружаем районы
  // ---------------------------------------------------
  regionSelect.addEventListener("change", async () => {
    const regionId = regionSelect.value;

    resetSelect(districtSelect, regionId ? "— выберите район —" : "— сначала выберите область —");
    resetSelect(schoolSelect, "— сначала выберите район —");
    districtSelect.disabled = !regionId;
    schoolSelect.disabled = true;

    if (!regionId) return;

    try {
      const districts = await fetchJSON(`/api/org/districts?region_id=${encodeURIComponent(regionId)}`);
      for (const d of districts) {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = d.name;
        districtSelect.appendChild(opt);
      }
    } catch (e) {
      console.error("Не удалось загрузить районы:", e);
    }
  });

  // ---------------------------------------------------
  // 3) При выборе района подгружаем школы
  // ---------------------------------------------------
  districtSelect.addEventListener("change", async () => {
    const districtId = districtSelect.value;

    resetSelect(schoolSelect, districtId ? "— выберите школу —" : "— сначала выберите район —");
    schoolSelect.disabled = !districtId;

    if (!districtId) return;

    try {
      const schools = await fetchJSON(`/api/org/schools?district_id=${encodeURIComponent(districtId)}`);
      for (const s of schools) {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.name;
        schoolSelect.appendChild(opt);
      }
    } catch (e) {
      console.error("Не удалось загрузить школы:", e);
    }
  });
});
