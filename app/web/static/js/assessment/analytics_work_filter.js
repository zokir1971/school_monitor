/* Filter changes invalidate the old work; never rewrite stored answers or scores. */
document.querySelectorAll('form[data-sm-quality-filter]').forEach(function (form) {
  form.addEventListener('change', function (event) {
    if (['academic_year_start', 'subject_id', 'grade_level', 'checkpoint'].includes(event.target.name)) {
      const work = form.elements.namedItem('work_key');
      if (work && work.value !== 'all') work.value = '';
    }
  });
});
