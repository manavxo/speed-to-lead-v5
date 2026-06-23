import { test, expect, Page } from '@playwright/test';

const MANAGER_PIN = '1234';
const REP_PIN = '7721';

async function loginAs(page: Page, pin: string) {
  await page.goto('/dashboard/login');
  await page.fill('input[name="dealer_slug"]', 'premier-auto');
  await page.fill('input[name="pin"]', pin);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard/leads');
}

test.describe('Dashboard E2E', () => {
  test.describe('Manager (PIN 1234)', () => {
    test.beforeEach(async ({ page }) => {
      await loginAs(page, MANAGER_PIN);
    });

    test('Leads page loads and shows leads', async ({ page }) => {
      await expect(page.locator('.lead-row')).toHaveCount(6);
      await expect(page).toHaveScreenshot('manager-leads.png');
    });

    test('Appointments page loads', async ({ page }) => {
      await page.click('a[href="/dashboard/appointments"]');
      await expect(page.locator('.appt-table-card')).toBeVisible();
    });

    test('Team page loads', async ({ page }) => {
      await page.click('a[href="/dashboard/team"]');
      await expect(page.locator('#leaderboard-table')).toBeVisible();
    });

    test('Settings page loads', async ({ page }) => {
      await page.click('a[href="/dashboard/settings"]');
      await expect(page.locator('.settings-tabs')).toBeVisible();
    });

    test('Stats page loads', async ({ page }) => {
      await page.click('a[href="/dashboard/stats"]');
      await expect(page.locator('.stats-grid')).toBeVisible();
    });

    test('New Lead form creates a lead', async ({ page }) => {
      await page.click('button:has-text("New Lead")');
      await expect(page.locator('#new-lead-modal')).toHaveClass(/show/);
      await page.fill('#new-lead-modal input[name="name"]', 'Grace Test');
      await page.fill('#new-lead-modal input[name="phone"]', '+17781110007');
      await page.fill('#new-lead-modal input[name="vehicle_ref"]', '2024 Audi Q5');
      await page.click('#new-lead-modal button[type="submit"]');
      await expect(page.locator('.lead-row')).toHaveCount(7);
    });

    test('Logout works', async ({ page }) => {
      await page.click('a[href="/dashboard/logout"]');
      await page.waitForURL('**/dashboard/login');
    });

    test('Sees Team and Settings nav links', async ({ page }) => {
      await expect(page.locator('a[href="/dashboard/team"]')).toBeVisible();
      await expect(page.locator('a[href="/dashboard/settings"]')).toBeVisible();
    });
  });

  test.describe('Rep Helly (PIN 7721)', () => {
    test.beforeEach(async ({ page }) => {
      await loginAs(page, REP_PIN);
    });

    test('Sees only own leads', async ({ page }) => {
      const leadCount = await page.locator('.lead-row').count();
      expect(leadCount).toBeLessThan(6);
      // Each visible lead should have assigned_rep "Helly"
      const repBadges = await page.locator('.lead-row .lead-rep').allTextContents();
      for (const badge of repBadges) {
        expect(badge).toContain('Helly');
      }
    });

    test('Does NOT see Team link in sidebar', async ({ page }) => {
      await expect(page.locator('aside a[href="/dashboard/team"]')).not.toBeVisible();
    });

    test('Does NOT see Settings link in sidebar', async ({ page }) => {
      await expect(page.locator('aside a[href="/dashboard/settings"]')).not.toBeVisible();
    });

    test('Team page redirects to Leads', async ({ page }) => {
      await page.goto('/dashboard/team');
      await page.waitForURL('**/dashboard/leads');
    });

    test('Settings page redirects to Leads', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForURL('**/dashboard/leads');
    });

    test('Stats page loads (My Stats)', async ({ page }) => {
      await page.goto('/dashboard/stats');
      await expect(page.locator('.stats-grid')).toBeVisible();
    });

    test('New Lead creates lead assigned to self', async ({ page }) => {
      await page.click('button:has-text("New Lead")');
      await page.fill('#new-lead-modal input[name="name"]', 'Helly Lead');
      await page.fill('#new-lead-modal input[name="phone"]', '+17781110008');
      await page.click('#new-lead-modal button[type="submit"]');
      await expect(page.locator('.lead-row')).toHaveCount(3);
    });

    test('Logout works', async ({ page }) => {
      await page.click('a[href="/dashboard/logout"]');
      await page.waitForURL('**/dashboard/login');
    });
  });
});
