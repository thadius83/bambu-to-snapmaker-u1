(function () {
  var backdrop = document.getElementById('contact-modal');
  var formWrap = document.getElementById('modal-form-wrap');
  var successEl = document.getElementById('modal-success');
  var errorEl = document.getElementById('modal-error');
  var msgEl = document.getElementById('contact-message');
  var emailEl = document.getElementById('contact-email');
  var submitBtn = document.getElementById('modal-submit');
  var cancelBtn = document.getElementById('modal-cancel');

  function openModal(e) {
    if (e) e.preventDefault();
    formWrap.style.display = '';
    successEl.style.display = 'none';
    errorEl.style.display = 'none';
    msgEl.value = '';
    emailEl.value = '';
    submitBtn.disabled = false;
    backdrop.classList.add('open');
    msgEl.focus();
  }

  function closeModal() {
    backdrop.classList.remove('open');
  }

  document.getElementById('contact-link').addEventListener('click', openModal);
  cancelBtn.addEventListener('click', closeModal);
  backdrop.addEventListener('click', function (e) {
    if (e.target === backdrop) closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeModal();
  });

  submitBtn.addEventListener('click', function () {
    var msg = msgEl.value.trim();
    if (!msg) {
      errorEl.textContent = 'Please enter a message.';
      errorEl.style.display = '';
      return;
    }
    errorEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';

    var body = new FormData();
    body.append('page', 'privacy');
    body.append('message', msg);
    body.append('email', emailEl.value.trim());

    fetch('/api/feedback', { method: 'POST', body: body })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function () {
        formWrap.style.display = 'none';
        successEl.style.display = '';
      })
      .catch(function () {
        errorEl.textContent = 'Something went wrong. Please try again.';
        errorEl.style.display = '';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Send';
      });
  });
})();
