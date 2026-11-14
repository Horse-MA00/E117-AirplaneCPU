/** ⓘ explanations: Esc closes an open tip; tips near the right edge open leftwards. Shared by /admin and /adaptive-pricing. */
const open = (info) => {
  info.classList.remove('dismissed');
  const box = info.getBoundingClientRect();
  info.classList.toggle('align-right', box.left + 380 > document.documentElement.clientWidth - 16);
};
document.addEventListener('mouseover', (event) => { const info = event.target.closest?.('.info'); if (info) open(info); });
document.addEventListener('focusin', (event) => { const info = event.target.closest?.('.info'); if (info) open(info); });
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  for (const info of document.querySelectorAll('.info:hover, .info:focus-within')) info.classList.add('dismissed');
});
