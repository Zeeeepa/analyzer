// Simple toast notifications
(function(){
  const container = document.getElementById('toastContainer');

  function toast(html, timeout=4000) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = html;
    container.appendChild(el);
    setTimeout(() => { el.remove(); }, timeout);
  }

  window.Toast = { show: toast };
})();

