let _csrfToken = null;

async function getCsrfToken() {
    if (!_csrfToken) {
        const resp = await fetch('/csrf_token');
        const data = await resp.json();
        _csrfToken = data.csrf_token;
    }
    return _csrfToken;
}

async function csrfPost(url, options = {}) {
    const token = await getCsrfToken();
    const headers = Object.assign({}, options.headers || {}, {
        'X-CSRF-Token': token
    });
    return fetch(url, Object.assign({}, options, { method: 'POST', headers: headers }));
}
