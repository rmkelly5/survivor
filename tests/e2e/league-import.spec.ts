import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const python = process.env.PYTHON || 'python';
const database = process.env.DATABASE_URL || 'sqlite:///browser-test.sqlite3';

function resetIsolatedFixtures() {
  if (!database.startsWith('sqlite:')) {
    throw new Error('Cutover browser tests require an isolated SQLite database.');
  }
  execFileSync(python, ['manage.py', 'seed_browser_smoke'], {
    env: {
      ...process.env,
      NEON_DATABASE_URL: '',
      DATABASE_URL: database,
      NFL_SEASON_YEAR: '2026',
      NFL_SEASON_START_DATE: new Date().toISOString().slice(0, 10),
    },
    stdio: 'pipe',
  });
}

function spreadsheet() {
  return execFileSync(python, ['-c', [
    'import io,sys',
    'from openpyxl import Workbook',
    'from openpyxl.styles import PatternFill',
    'w=Workbook();s=w.active;s.title="Survivor Pool"',
    's.append(["Week","browser_user","rival_player"])',
    's.append([1,"Bills","Dolphins"]);s.append([2,"Dolphins","Bills"]);s.append([3,None,None])',
    's["B2"].fill=s["C3"].fill=PatternFill("solid",fgColor="B6D7A8")',
    's["C2"].fill=s["B3"].fill=PatternFill("solid",fgColor="E06666")',
    's.append(["Losses:",1,1]);s.append(["$ Owed:",60,75]);s.append(["Total Pot:",135])',
    'b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())',
  ].join('\n')]);
}

test.describe('Staff spreadsheet cutover', () => {
  test.beforeEach(resetIsolatedFixtures);
  test.afterEach(resetIsolatedFixtures);

  test('upload, review, confirmed replacement, backup, and audited override', async ({ page }, testInfo) => {
    await page.goto('/members/login/');
    await page.locator('[name="username"]').fill('admin_user');
    await page.locator('[name="password"]').fill('Test4321!');
    await page.getByRole('button', { name: 'Login', exact: true }).click();
    await page.goto('/league-operations/');
    await page.locator('a[href="/league-operations/import/"]').click();
    await expect(page.getByRole('heading', { name: 'Import the pool history' })).toBeVisible();
    await page.locator('[name="file"]').setInputFiles({
      name: 'league.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: spreadsheet(),
    });
    await page.locator('[name="completed_week"]').fill('2');
    await page.getByRole('button', { name: 'Upload and review', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Check the history before replacement' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirm and replace history' })).toHaveCount(0);
    await page.locator('[name="loss_0_2"]').selectOption('standard');
    await page.locator('[name="loss_1_1"]').selectOption('favorite');
    await page.getByRole('button', { name: 'Save review and validate' }).click();
    await expect(page.getByRole('button', { name: 'Confirm and replace history' })).toBeVisible();
    await expect(page.locator('.li-totals-panel')).toContainText('135'); // displayed in individual totals below
    await page.screenshot({ path: testInfo.outputPath('cutover-review.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await page.locator('[name="confirmation"]').fill('REPLACE 2026');
    await page.locator('[name="ack_replace"]').check();
    await page.locator('[name="ack_omitted"]').check();
    await page.getByRole('button', { name: 'Confirm and replace history' }).click();
    await expect(page.getByRole('heading', { name: 'This batch has been applied' })).toBeVisible();
    await expect(page.locator('.li-applied')).toContainText('4 picks imported');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Open saved backup' }).click();
    const download = await downloadPromise;
    const downloadPath = await download.path();
    expect(downloadPath).not.toBeNull();
    const backup = JSON.parse(readFileSync(downloadPath!, 'utf8'));
    expect(backup.backup.picks.length).toBeGreaterThan(4);
    expect(backup.import_summary.total).toBe('135.00');
    expect(JSON.stringify(backup)).not.toContain('Test4321!');
    await page.goto('/league-operations/loss-overrides/');
    const imported = page.locator('.li-override-row').filter({ hasText: 'browser_user' });
    await expect(imported).toContainText('Imported loss');
    await expect(imported.locator('option[value="auto"]')).toHaveCount(0);
    await imported.locator('[name="override"]').selectOption('favorite');
    await imported.locator('[name="reason"]').fill('Confirmed historical favorite correction');
    await imported.getByRole('button', { name: 'Save override' }).click();
    await expect(page.locator('.li-audit-panel')).toContainText('Confirmed historical favorite correction');
    await page.goto('/league_leaderboard/');
    await expect(page.locator('body')).toContainText('browser_user');
  });
});
