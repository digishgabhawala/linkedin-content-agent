import { defineConfig, devices } from '@playwright/test'

const backendPort = 11100
const frontendPort = 11101
const databasePath = `/private/tmp/linkedin-content-agent-playwright-${process.pid}.db`

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}/linkedin/`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: 'mobile-chromium',
      use: {
        ...devices['iPhone 13'],
        browserName: 'chromium',
      },
    },
  ],
  webServer: [
    {
      command: [
        'DATABASE_URL=sqlite:////' + databasePath.replace(/^\//, ''),
        'AUTH_ENABLED=false',
        'AUTO_INIT_DB=true',
        `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      ].join(' '),
      cwd: '../backend',
      url: `http://127.0.0.1:${backendPort}/api/linkedin/auth/config`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `VITE_API_PROXY_TARGET=http://127.0.0.1:${backendPort} npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      cwd: '.',
      url: `http://127.0.0.1:${frontendPort}/linkedin/`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
