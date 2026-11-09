// Recette réelle : aucun fournisseur externe ni dépense, API OSIA sur PostgreSQL de test.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.argv[2];

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const failures = [];
    page.on('pageerror', error => failures.push(error.message));
    await page.route('**/*', route => route.request().url().startsWith(base + '/') ? route.continue() : route.abort());
    await page.goto(base);
    await page.locator('#auth-dialog[open]').waitFor();
    await page.locator('#auth-token').fill(process.env.OSIA_BROWSER_TOKEN);
    await page.getByRole('button', { name: 'Se connecter', exact: true }).click();
    await page.getByRole('heading', { name: 'Nouvelle investigation' }).waitFor();
    assert.equal(await page.locator('#auth-token').inputValue(), '');

    await page.getByRole('link', { name: 'Paramètres', exact: true }).click();
    await page.locator('#ai-provider').selectOption('local');
    await page.locator('#ai-model').fill('test-local');
    await page.locator('#ai-model').press('Tab');
    await page.locator('form').filter({ has: page.locator('#ai-model') }).getByRole('button', { name: 'Enregistrer', exact: true }).click();
    await page.getByText('Configuration enregistrée', { exact: false }).waitFor();
    // La configuration peut être enregistrée sans lancer d’appel de modèle.
    const providers = await page.evaluate(async () => (await fetch('/api/v1/ai/providers', {
      headers: { Authorization: 'Bearer ' + sessionStorage.getItem('osia_token') }
    })).json());
    assert.equal(providers.configurations.local.model, 'test-local');
    assert.equal(providers.selected, 'simulated');

    // La liste des investigations peut rester en attente pendant un lancement.
    let releaseList;
    const listPending = new Promise(resolve => { releaseList = resolve; });
    await page.route('**/api/v1/investigations', async route => {
      if (route.request().method() === 'GET') await listPending;
      await route.continue();
    });
    const listRequested = page.waitForRequest(req => req.url() === base + '/api/v1/investigations' && req.method() === 'GET');
    try {
      await page.getByRole('link', { name: 'OSIA', exact: true }).click();
      await listRequested;
      await page.locator('input[name="title"]').fill('Recette navigateur');
      await page.locator('textarea[name="hints"]').fill('indice de test');
      await page.getByRole('button', { name: 'Lancer la recherche' }).click();
      await page.getByRole('heading', { name: 'Recette navigateur', exact: true }).waitFor();
    } finally {
      releaseList();
    }
    await page.getByText('arrêtée', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Reprendre', exact: true }).count(), 0);
    assert.equal(await page.getByText('Appels payants désactivés.', { exact: false }).count(), 1);
    const investigationHash = await page.evaluate(() => location.hash);

    // Les erreurs d’import ne doivent jamais apparaître comme un succès.
    await page.getByText('Import supervisé d’une archive .osia (T7.6)', { exact: true }).click();
    await page.locator('#import-file').setInputFiles({ name: 'invalid.osia', mimeType: 'application/zip', buffer: Buffer.from('not a zip') });
    await page.getByRole('button', { name: 'Prévisualiser', exact: true }).click();
    await page.locator('#import-preview').filter({ hasText: 'Prévisualisation refusée' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Appliquer (ajout)', exact: true }).isDisabled(), true);
    // Un refus après une prévisualisation réussie n’est pas un import appliqué.
    await page.route('**/api/v1/import/preview', route => route.fulfill({ json: { counts: {} } }));
    await page.getByRole('button', { name: 'Prévisualiser', exact: true }).click();
    await page.getByRole('button', { name: 'Appliquer (ajout)', exact: true }).click();
    await page.locator('#import-preview').filter({ hasText: 'Import refusé' }).waitFor();
    assert.ok(!(await page.locator('#import-preview').textContent()).includes('Import appliqué'));

    // Une réponse lente de l’ancienne investigation ne remplace pas la page Paramètres.
    await page.getByRole('link', { name: 'Paramètres', exact: true }).click();
    await page.getByRole('heading', { name: 'Paramètres', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.OSIA.state.sseAbort), null);
    let release;
    let started;
    const pending = new Promise(resolve => { release = resolve; });
    const intercepted = new Promise(resolve => { started = resolve; });
    await page.route('**/api/v1/investigations/*', async route => {
      if (/\/api\/v1\/investigations\/[^/?]+$/.test(route.request().url())) {
        started();
        await pending;
      }
      await route.continue();
    });
    await page.evaluate(hash => { location.hash = hash; }, investigationHash);
    await intercepted;
    await page.getByRole('link', { name: 'Paramètres', exact: true }).click();
    release();
    await page.getByRole('heading', { name: 'Paramètres', exact: true }).waitFor();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('#layout').count(), 0);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.locator('#ai-provider').isVisible());

    await page.getByRole('button', { name: "Jeton d'accès", exact: true }).click();
    await page.getByRole('button', { name: 'Se déconnecter', exact: true }).click();
    await page.getByText('Connecte-toi pour accéder aux investigations.', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => sessionStorage.getItem('osia_token')), null);
    assert.equal(await page.locator('#layout').count(), 0);
    assert.deepEqual(failures, []);
    console.log('Chromium : connexion, paramètres, investigation, erreurs d’import, navigation et déconnexion validés.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
