const $ = (id) => document.getElementById(id);
let submitting = false;

function clearError() {
  $('login-error').textContent = '';
  $('login-error').hidden = true;
  $('login-email').removeAttribute('aria-invalid');
  $('login-password').removeAttribute('aria-invalid');
}
function setBusy(value) {
  submitting = value;
  $('login-fields').disabled = value;
  $('demo-member').disabled = value;
  $('demo-guest').disabled = value;
  $('login-submit').textContent = value ? 'Signing in…' : 'Sign in';
  $('login-form').setAttribute('aria-busy', String(value));
}
function fillAccount(email) {
  if (submitting) return;
  clearError();
  $('login-email').value = email;
  $('login-password').value = 'FlyPass399!';
  $('login-status').textContent = 'Demo credentials filled. Select Sign in to continue.';
  $('login-submit').focus();
}
$('demo-member').addEventListener('click', () => fillAccount('member@uoption.test'));
$('demo-guest').addEventListener('click', () => fillAccount('guest@uoption.test'));
$('toggle-password').addEventListener('click', () => {
  const show = $('login-password').type === 'password';
  $('login-password').type = show ? 'text' : 'password';
  $('toggle-password').textContent = show ? 'Hide' : 'Show';
  $('toggle-password').setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  $('toggle-password').setAttribute('aria-pressed', String(show));
});
$('toggle-password').setAttribute('aria-label', 'Show password');
for (const id of ['login-email', 'login-password']) $(id).addEventListener('input', clearError);
$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (submitting || !$('login-form').reportValidity()) return;
  clearError();
  $('login-status').textContent = '';
  const credentials = { email: $('login-email').value.trim(), password: $('login-password').value };
  setBusy(true);
  try {
    const response = await fetch('/api/member-portal/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(credentials),
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        $('login-email').setAttribute('aria-invalid', 'true');
        $('login-password').setAttribute('aria-invalid', 'true');
      }
      throw new Error(data.error || 'Sign in could not be completed. Please try again.');
    }
    if (!data.authenticated) throw new Error('The account session could not be confirmed. Please try again.');
    $('login-password').value = '';
    $('login-status').textContent = 'Signed in. Opening your account…';
    location.assign('/members');
  } catch (error) {
    $('login-error').textContent =
      error instanceof TypeError || error instanceof SyntaxError
        ? 'We could not reach the sign-in service. Please try again.'
        : error.message;
    $('login-error').hidden = false;
    setBusy(false);
    $('login-email').focus();
  }
});
async function showCurrentSession() {
  try {
    const response = await fetch('/api/member-portal/session', { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) return;
    const session = await response.json();
    if (!session.authenticated || !session.user) return;
    $('current-session-name').textContent = session.user.email;
    $('current-session').hidden = false;
  } catch {
    /* The form remains available if the optional session preview fails. */
  }
}
setBusy(false);
showCurrentSession();
