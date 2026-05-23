/* mobile-nav.js
 *
 * Solo en pantallas chicas (≤768px), inyecta un botón hamburger en la topbar
 * y un overlay para abrir/cerrar el sidebar como drawer. No-op si la página
 * no tiene `.sidebar` (login, pricing, onboarding).
 *
 * Carga este script al final del body via:
 *   <script src="/mobile-nav.js" defer></script>
 */
(function () {
  function init() {
    var sidebar = document.querySelector('.sidebar');
    var topbar  = document.querySelector('.topbar');
    if (!sidebar || !topbar) return;
    if (document.querySelector('.sm-menu-btn')) return; // ya inyectado

    // Botón hamburger
    var btn = document.createElement('button');
    btn.className = 'sm-menu-btn';
    btn.setAttribute('aria-label', 'Abrir menú');
    btn.innerHTML = '☰'; // ☰
    topbar.insertBefore(btn, topbar.firstChild);

    // Overlay para cerrar al tocar fuera
    var overlay = document.createElement('div');
    overlay.className = 'sm-sidebar-overlay';
    document.body.appendChild(overlay);

    function open() {
      sidebar.classList.add('open');
      overlay.classList.add('open');
      document.body.style.overflow = 'hidden';
    }
    function close() {
      sidebar.classList.remove('open');
      overlay.classList.remove('open');
      document.body.style.overflow = '';
    }

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (sidebar.classList.contains('open')) close(); else open();
    });
    overlay.addEventListener('click', close);

    // Cerrar al navegar dentro del sidebar (click en un item / link)
    sidebar.addEventListener('click', function (e) {
      var target = e.target;
      while (target && target !== sidebar) {
        if (target.matches('a, .sidebar-item')) {
          // pequeño delay para que el click registre antes del cierre
          setTimeout(close, 50);
          break;
        }
        target = target.parentNode;
      }
    });

    // Cerrar con tecla Esc (útil en desktop accesibilidad)
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
