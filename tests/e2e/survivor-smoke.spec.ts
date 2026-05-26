import { expect, type Page, type TestInfo, test } from '@playwright/test';

const brokenTextPattern = /(?:â|Â|ðŸ|�)/;
const criticalResourceTypes = new Set(['document', 'stylesheet', 'script']);

async function watchPage(page: Page) {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });

  page.on('requestfailed', (request) => {
    if (criticalResourceTypes.has(request.resourceType())) {
      failedRequests.push(`${request.resourceType()} ${request.url()} ${request.failure()?.errorText || ''}`);
    }
  });

  return {
    assertClean() {
      expect(consoleErrors, 'browser console errors').toEqual([]);
      expect(failedRequests, 'failed document/CSS/JS requests').toEqual([]);
    },
  };
}

async function expectNoBrokenText(page: Page) {
  const bodyText = await page.locator('body').innerText();
  expect(bodyText).not.toMatch(brokenTextPattern);
}

async function expectReadableButton(page: Page, name: string) {
  const link = page.getByRole('link', { name });
  const target = (await link.count()) ? link.first() : page.getByRole('button', { name });
  await expect(target).toBeVisible();
  const colors = await target.evaluate((el) => {
    const style = getComputedStyle(el);
    return {
      color: style.color,
      background: style.backgroundColor,
    };
  });
  expect(colors.color).not.toEqual(colors.background);
}

async function login(page: Page) {
  await page.goto('/members/login/');
  await page.locator('input[name="username"]').fill('browser_user');
  await page.locator('input[name="password"]').fill('Test4321!');
  await page.getByRole('button', { name: 'Login' }).click();
  await expect(page.getByRole('heading', { name: /browser_user's Picks/i })).toBeVisible();
}

async function capture(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

test('anonymous pages render cleanly', async ({ page }, testInfo) => {
  const monitor = await watchPage(page);

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Survivor Pool' })).toBeVisible();
  await expect(page.locator('.container').getByRole('link', { name: 'Login' })).toBeVisible();
  await expectReadableButton(page, 'Login');
  await expectNoBrokenText(page);
  await capture(page, testInfo, 'anonymous-home');

  await page.goto('/members/login/');
  await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible();
  await expectReadableButton(page, 'Login');
  await expectNoBrokenText(page);

  await page.goto('/members/register/');
  await expect(page.getByRole('heading', { name: 'Register' })).toBeVisible();
  await expectReadableButton(page, 'Create Account');
  await expectNoBrokenText(page);

  await page.goto('/rules/');
  await expect(page.getByRole('heading', { name: 'League Rules' })).toBeVisible();
  await expectNoBrokenText(page);

  monitor.assertClean();
});

test('authenticated navigation pages render cleanly', async ({ page }, testInfo) => {
  const monitor = await watchPage(page);

  await login(page);
  const pages = [
    ['/allPicks/', '2026 League Picks'],
    ['/league_leaderboard/', '2026 Leaderboard'],
    ['/pot/', '2026 Pot'],
    ['/rules/', 'League Rules'],
    ['/chat/', 'League Chat'],
  ] as const;

  for (const [url, heading] of pages) {
    await page.goto(url);
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
    await expectNoBrokenText(page);
  }

  await expect(page.locator('#chat-messages .chat-message')).toHaveCount(190);
  await expect(page.locator('#chat-messages .chat-message--system')).toHaveCount(2);
  await page.goto('/');
  await expect(page.locator('#chat-widget')).not.toHaveClass(/is-open/);
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await expect(page.locator('#chat-widget')).toHaveClass(/is-open/);
  await expect(page.locator('#chat-widget-messages .chat-message')).toHaveCount(190);
  await capture(page, testInfo, 'league-chat');
  monitor.assertClean();
});

test('make a pick defaults to current week and supports outer weeks', async ({ page }, testInfo) => {
  const monitor = await watchPage(page);

  await login(page);
  await expect(page.locator('.pick-card')).toHaveCount(7);
  await expect(page.getByRole('link', { name: '+ Make a Pick' })).toBeVisible();
  await expectReadableButton(page, '+ Make a Pick');

  await page.goto('/add_pick/');

  await expect(page.getByRole('heading', { name: 'Make Your Pick' })).toBeVisible();
  await expect(page.locator('select[name="week"]')).toHaveValue('1');
  await expect(page.locator('.matchup-card')).toHaveCount(3);
  await expect(page.getByRole('button', { name: 'Submit Pick' })).toBeDisabled();
  await expectNoBrokenText(page);

  await page.locator('select[name="week"]').selectOption('7');
  await page.waitForURL(/week=7/);
  await expect(page.locator('select[name="week"]')).toHaveValue('7');
  await expect(page.locator('.matchup-card')).toHaveCount(3);
  await expect(page.locator('label.team-card', { hasText: 'Bills' }).locator('input[name="team"]')).toBeDisabled();

  await page.locator('label.team-card', { hasText: 'Patriots' }).click();
  await expect(page.getByText('Selected: Patriots')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit Pick' })).toBeEnabled();
  await capture(page, testInfo, 'make-pick-week-7');

  monitor.assertClean();
});

test('mobile nav and league picks stay usable', async ({ page, isMobile }, testInfo) => {
  test.skip(!isMobile, 'mobile-only layout smoke');
  const monitor = await watchPage(page);

  await login(page);
  await page.goto('/allPicks/');
  await expect(page.getByRole('heading', { name: '2026 League Picks' })).toBeVisible();
  await expect(page.locator('.week-summary-panel')).toBeVisible();
  await expect(page.locator('.picks-table tbody tr')).toHaveCount(7);
  await capture(page, testInfo, 'mobile-league-picks');

  const nav = page.locator('#navbarSupportedContent');
  await expect(nav).not.toBeVisible();
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await expect(nav).toBeVisible();
  await expect(page.getByRole('link', { name: 'Make A Pick' })).toBeVisible();
  await page.getByRole('button', { name: 'League Chat' }).click();
  await expect(page.locator('#chat-widget')).toHaveClass(/is-open/);
  await page.locator('#chat-widget-close').click();
  await expect(page.locator('#chat-widget')).not.toHaveClass(/is-open/);

  await page.getByRole('link', { name: 'Make A Pick' }).click();
  await expect(page.getByRole('heading', { name: 'Make Your Pick' })).toBeVisible();
  await expect(page.locator('.team-card').first()).toBeVisible();
  await expectNoBrokenText(page);

  monitor.assertClean();
});
