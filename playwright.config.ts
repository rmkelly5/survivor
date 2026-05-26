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
      `${quotedPython} manage.py runserver 127.0.0.1:8005`,
    ].join(' && '),
    url: 'http://127.0.0.1:8005',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      DJANGO_DEBUG: 'True',
      DJANGO_ALLOWED_HOSTS: 'localhost,127.0.0.1,testserver',
      DATABASE_URL: process.env.DATABASE_URL || 'sqlite:///browser-test.sqlite3',
      NFL_SEASON_YEAR: '2026',
      NFL_SEASON_START_DATE: '2026-09-09',
    },
  },
  projects: [
    {
      name: 'desktop-chrome',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
        channel: 'chrome',
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
