(() => {
  const entry = document.querySelector("[data-staff-entry-url]");
  if (!entry) {
    return;
  }

  let clicks = 0;
  let resetTimer;

  entry.addEventListener("click", () => {
    clicks += 1;
    clearTimeout(resetTimer);
    if (clicks === 3) {
      window.location.assign(entry.dataset.staffEntryUrl);
      return;
    }
    resetTimer = setTimeout(() => {
      clicks = 0;
    }, 1200);
  });
})();
