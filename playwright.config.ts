import { defineConfig, devices } from '@playwright/test';

const pythonCommand = process.env.PYTHON || 'python';
const quotedPython = /\s/.test(pythonCommand) && !pythonCommand.startsWith('"')
  ? `"${pythonCommand}"`
  : pythonCommand;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8005',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: [
      `${quotedPython} manage.py migrate --noinput`,
      `${quotedPython} manage.py seed_browser_smoke`,
      // Avoid Django's Windows autoreloader leaving a child process behind when
      // Playwright tears down the web server after a run.
      `${quotedPython} manage.py runserver 127.0.0.1:8005 --noreload`,
    ].join(' && '),
    url: 'http://127.0.0.1:8005',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      DJANGO_DEBUG: 'True',
      DJANGO_LOCAL_HTTP: '1',
      DJANGO_ALLOWED_HOSTS: 'localhost,127.0.0.1,testserver',
      NEON_DATABASE_URL: '',
      DATABASE_URL: process.env.DATABASE_URL || 'sqlite:///browser-test.sqlite3',
      NFL_SEASON_YEAR: '2026',
      // Keep the Week 1 fixture stable as the real calendar advances.
      NFL_SEASON_START_DATE: new Date().toISOString().slice(0, 10),
    },
  },
  projects: [
    // Most members use iPhones; Chromium emulation alone misses Safari regressions.
    { name: 'iphone-webkit', use: { ...devices['iPhone 13'] } },
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: 'mobile-chromium',
      use: {
        ...devices['Pixel 5'],
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
