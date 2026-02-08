// Minimal modal utilities
(function(){
  const modal = document.getElementById('logsModal');
  const closeBtn = document.getElementById('closeLogsBtn');

  closeBtn.addEventListener('click', () => hideLogsModal());
  modal.addEventListener('click', (e) => {
    if (e.target === modal) hideLogsModal();
  });

  window.showLogsModal = function() {
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  };
  window.hideLogsModal = function() {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  };
})();

