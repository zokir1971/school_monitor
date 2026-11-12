(() => {
  'use strict';
  const form = document.querySelector('[data-progress-filter]');
  if (!form) return;
  const district = form.querySelector('[name="district_id"]');
  const school = form.querySelector('[name="school_id"]');
  const classes = form.querySelector('[name="class_id"]');
  const message = form.querySelector('[data-classes-message]');
  const ru = form.dataset.language === 'ru';
  let pending;
  let sequence = 0;
  const resetClasses = () => {
    classes.replaceChildren(new Option(school.value ? (ru ? 'Все классы' : 'Барлық сынып') : (ru ? 'Сначала выберите школу' : 'Алдымен мектепті таңдаңыз'), ''));
    classes.disabled = true;
  };
  async function updateOptions(changedDistrict) {
    const current = ++sequence;
    if (pending) pending.abort();
    if (changedDistrict) {
      school.replaceChildren(new Option(ru ? 'Все школы' : 'Барлық мектеп', ''));
      school.disabled = true;
    }
    resetClasses();
    message.hidden = true;
    if (!changedDistrict && !school.value) return;
    pending = new AbortController();
    const url = new URL(form.dataset.classesUrl, window.location.origin);
    if (district && district.value) url.searchParams.set('district_id', district.value);
    if (school.value) url.searchParams.set('school_id', school.value);
    try {
      const response = await fetch(url, {signal: pending.signal, credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if (!response.ok) throw new Error('options');
      const data = await response.json();
      if (current !== sequence) return;
      if (!Array.isArray(data.schools) || !Array.isArray(data.classes)) throw new Error('options');
      if (changedDistrict) {
        for (const item of data.schools) school.add(new Option(item.name, String(item.id)));
        school.disabled = false;
      }
      for (const item of data.classes) classes.add(new Option(item.name, String(item.id)));
      classes.disabled = !school.value;
    } catch (error) {
      if (error.name === 'AbortError' || current !== sequence) return;
      school.disabled = false;
      message.textContent = ru ? 'Не удалось загрузить список. Нажмите «Показать», чтобы обновить школы и классы.' : 'Тізім жүктелмеді. Мектептер мен сыныптарды жаңарту үшін «Көрсету» түймесін басыңыз.';
      message.hidden = false;
    }
  }
  if (district) district.addEventListener('change', () => updateOptions(true));
  school.addEventListener('change', () => updateOptions(false));
})();
