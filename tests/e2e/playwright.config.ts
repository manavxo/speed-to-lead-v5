import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 90000,
  // Single worker + no retries: the suite shares one server/DB, and the
  // create-lead tests mutate it, so runs must be serial and not double-submit.
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    screenshot: 'on',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python run_server.py',
    url: 'http://127.0.0.1:8000/dashboard/login',
    reuseExistingServer: false,
    timeout: 120000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile',
      use: { ...devices['iPhone 13'] },
    },
  ],
});
