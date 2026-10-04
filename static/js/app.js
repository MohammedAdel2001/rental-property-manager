const menuButton = document.querySelector('.menu-toggle');
const sidebar = document.querySelector('.sidebar');
const mobileLayout = window.matchMedia('(max-width: 760px)');

function updateNavigation() {
  const open = document.body.classList.contains('nav-open');
  menuButton?.setAttribute('aria-expanded', String(open));
  if (sidebar) sidebar.inert = mobileLayout.matches && !open;
}

menuButton?.addEventListener('click', () => {
  document.body.classList.toggle('nav-open');
  updateNavigation();
});
mobileLayout.addEventListener('change', updateNavigation);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.body.classList.contains('nav-open')) {
    document.body.classList.remove('nav-open');
    updateNavigation();
    menuButton?.focus();
  }
});
document.querySelectorAll('.dismiss-message').forEach(button => {
  button.addEventListener('click', () => button.closest('.message').remove());
});
updateNavigation();
