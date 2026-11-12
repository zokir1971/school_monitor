document.addEventListener("DOMContentLoaded", () => {
  const sel = document.getElementById("positionSelect");
  const other = document.getElementById("positionOther");

  if (!sel || !other) return;

  function sync(){
    const isOther = sel.value === "__other__";
    other.style.display = isOther ? "block" : "none";
    if (isOther) other.required = true;
    else other.required = false;
  }

  sel.addEventListener("change", sync);
  sync();
});
