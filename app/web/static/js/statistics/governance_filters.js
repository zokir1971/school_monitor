/* A district is an administrative group; regional schools keep their address. */
document.querySelectorAll('form').forEach(function (form) {
  const governance = form.querySelector('select[name="governance"]');
  const district = form.querySelector('select[name="district_id"]');
  if (!governance || !district) return;
  governance.addEventListener('change', function () {
    if (governance.value === 'region') district.value = '';
  });
  district.addEventListener('change', function () {
    if (district.value) governance.value = 'district';
  });
});
