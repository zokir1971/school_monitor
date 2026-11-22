(() => {
  const form = document.querySelector('.sa-filters');
  if (!form) return;
  const region = form.elements.namedItem('region_id');
  region.addEventListener('change', () => { form.elements.namedItem('district_id').value = ''; form.elements.namedItem('district_id').disabled = true; });
  for (const name of ['start', 'end']) {
    form.elements.namedItem(name).addEventListener('change', () => { form.elements.namedItem('period').value = 'custom'; });
  }
})();
