/* ── PT ATIKA JAYA SAMUDERA – Main JS ── */

// ── NAV SCROLL EFFECT ──
(function () {
  const nav = document.querySelector('.landing-nav');
  if (!nav) return;
  const toggle = () => nav.classList.toggle('scrolled', window.scrollY > 30);
  window.addEventListener('scroll', toggle);
  toggle();
})();

// ── MOBILE HAMBURGER ──
(function () {
  const btn = document.querySelector('.nav-hamburger');
  const links = document.querySelector('.nav-links');
  if (!btn || !links) return;
  btn.addEventListener('click', () => links.classList.toggle('open'));
})();

// ── SIDEBAR TOGGLE (PANEL) ──
(function () {
  const toggle  = document.querySelector('.topbar-toggle');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');
  if (!toggle) return;

  const open = () => { sidebar.classList.add('open'); overlay.classList.add('show'); };
  const close = () => { sidebar.classList.remove('open'); overlay.classList.remove('show'); };

  toggle.addEventListener('click', open);
  overlay && overlay.addEventListener('click', close);
})();

// ── ACTIVE SIDEBAR LINK ──
(function () {
  const links = document.querySelectorAll('.sidebar-link');
  const path  = window.location.pathname;
  links.forEach(a => {
    if (a.getAttribute('href') && path.startsWith(a.getAttribute('href')) && a.getAttribute('href') !== '/') {
      a.classList.add('active');
    }
  });
})();

// ── AUTO-DISMISS ALERTS ──
(function () {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(a => {
    setTimeout(() => {
      a.style.transition = 'opacity .4s';
      a.style.opacity = '0';
      setTimeout(() => a.remove(), 400);
    }, 4000);
  });
})();

// ── OCEAN PARTICLE BACKGROUND ──
(function () {
  const canvas = document.getElementById('particles-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, particles = [];

  const resize = () => { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; };
  window.addEventListener('resize', resize);
  resize();

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x = Math.random() * W;
      this.y = Math.random() * H;
      this.r = Math.random() * 1.5 + 0.3;
      this.opacity = Math.random() * 0.4 + 0.05;
      this.speed = Math.random() * 0.3 + 0.05;
      this.dx = (Math.random() - 0.5) * 0.3;
    }
    update() {
      this.y -= this.speed;
      this.x += this.dx;
      if (this.y < -5 || this.x < -5 || this.x > W + 5) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(77,182,245,${this.opacity})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < 80; i++) particles.push(new Particle());

  (function loop() {
    ctx.clearRect(0, 0, W, H);
    particles.forEach(p => { p.update(); p.draw(); });
    requestAnimationFrame(loop);
  })();
})();

// ── DELETE CONFIRM ──
document.addEventListener('click', function (e) {
  const btn = e.target.closest('[data-confirm]');
  if (!btn) return;
  const msg = btn.dataset.confirm || 'Yakin ingin menghapus data ini?';
  if (!confirm(msg)) e.preventDefault();
});

// ── COUNTER ANIMATION ──
(function () {
  const counters = document.querySelectorAll('[data-count]');
  if (!counters.length) return;

  const animCount = el => {
    const target = +el.dataset.count;
    const dur = 1500;
    const start = performance.now();
    const tick = now => {
      const p = Math.min((now - start) / dur, 1);
      el.textContent = Math.floor(p * target) + (el.dataset.suffix || '');
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { animCount(e.target); obs.unobserve(e.target); } });
  }, { threshold: .3 });

  counters.forEach(c => obs.observe(c));
})();

// ── FADE-IN ON SCROLL ──
(function () {
  const els = document.querySelectorAll('[data-fade]');
  if (!els.length) return;
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('animate-fade-up'); obs.unobserve(e.target); } });
  }, { threshold: .1 });
  els.forEach(el => obs.observe(el));
})();
