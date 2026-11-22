(() => {
  const form = document.querySelector('.ts-filters');
  const region = form?.elements.namedItem('region_id');
  if (!form || !region || region.type === 'hidden') return;
  const district = form.elements.namedItem('district_id');
  const view = form.elements.namedItem('view');
  region.addEventListener('change', () => {
    if (district) { district.value = ''; district.disabled = true; }
    form.elements.namedItem('direction_id').value = '';
    // The server chooses the appropriate territorial level after submission.
    if (view) view.disabled = true;
  });
  district?.addEventListener('change', () => { if (view) view.disabled = true; });
})();
