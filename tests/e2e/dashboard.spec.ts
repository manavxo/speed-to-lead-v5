import { test, expect, Page } from '@playwright/test';

// PINs come from dealers/premier-auto.yaml (manager_pin + per-rep pin).
const DEALER = 'premier-auto';
const MANAGER = { name: 'Manager', pin: '1234' };
const HELLY = { name: 'Helly', pin: '7721' };

// The leads list renders one .lead-card per lead inside #leads-list, both on
// initial load and after the htmx reload/filter (leads_partial.html).
const LEAD_CARD = '#leads-list .lead-card';
const REP_TAG = `${LEAD_CARD} .lead-rep`;

async function loginAs(page: Page, who: { name: string; pin: string }) {
  // dealer_slug in the query string makes login_page populate the rep dropdown.
  await page.goto(`/dashboard/login?dealer_slug=${DEALER}`);
  await page.selectOption('select[name="rep_name"]', who.name);
  await page.fill('input[name="pin"]', who.pin);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard/leads');
}

async function logout(page: Page) {
  // Two logout links exist (sidebar + mobile bar); click whichever is visible.
  await page.locator('a[href="/dashboard/logout"]:visible').first().click();
  await page.waitForURL('**/dashboard/login');
}

async function createLead(page: Page, name: string, phone: string, vehicle?: string) {
  // Wait for the list to render before counting, so `before` isn't a stale 0.
  await expect(page.locator(LEAD_CARD).first()).toBeVisible();
  const before = await page.locator(LEAD_CARD).count();
  await page.click('button:has-text("New Lead")');
  await expect(page.locator('#new-lead-modal')).toHaveClass(/show/);
  await page.fill('#new-lead-modal input[name="name"]', name);
  await page.fill('#new-lead-modal input[name="phone"]', phone);
  if (vehicle) await page.fill('#new-lead-modal input[name="vehicle_ref"]', vehicle);
  // Creation round-trips through the lead pipeline; the first create in a fresh
  // process is slow (conversation-engine cold start), so wait for the POST.
  const created = page.waitForResponse(
    (r) => r.url().includes('/dashboard/leads/new') && r.request().method() === 'POST',
    { timeout: 40000 },
  );
  await page.click('#new-lead-modal button[type="submit"]');
  await created;
  // List reloads via htmx (HX-Trigger: reload-leads) after the POST.
  await expect(page.locator(LEAD_CARD)).toHaveCount(before + 1, { timeout: 15000 });
}

test.describe('Dashboard E2E', () => {
  test.describe('Manager (PIN 1234)', () => {
    test.beforeEach(async ({ page }) => {
      await loginAs(page, MANAGER);
    });

    test('Leads page shows all seeded leads', async ({ page }) => {
      await expect(page.locator(LEAD_CARD).first()).toBeVisible();
      expect(await page.locator(LEAD_CARD).count()).toBeGreaterThanOrEqual(6);
    });

    test('Appointments page loads', async ({ page }) => {
      await page.goto('/dashboard/appointments');
      await expect(page.locator('.appt-table-card')).toBeVisible();
    });

    test('Team page loads', async ({ page }) => {
      await page.goto('/dashboard/team');
      await expect(page.locator('#leaderboard-table')).toBeVisible();
    });

    test('Settings page loads', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await expect(page.locator('.settings-tabs')).toBeVisible();
    });

    test('Stats page loads', async ({ page }) => {
      await page.goto('/dashboard/stats');
      await expect(page.locator('.stats-grid')).toBeVisible();
    });

    test('Sees Team and Settings nav links', async ({ page }) => {
      expect(await page.locator('a[href="/dashboard/team"]').count()).toBeGreaterThan(0);
      expect(await page.locator('a[href="/dashboard/settings"]').count()).toBeGreaterThan(0);
    });

    test('New Lead form creates a lead', async ({ page }) => {
      await createLead(page, 'Grace Test', '+17781110007', '2024 Audi Q5');
    });

    test('Logout works', async ({ page }) => {
      await logout(page);
    });

    test('Login dropdown lists only active reps', async ({ page }) => {
      // After logout, land on login page with dealer_slug — verify the dropdown
      await page.goto(`/dashboard/login?dealer_slug=${DEALER}`);
      const options = await page.locator('select[name="rep_name"] option').allTextContents();
      expect(options).toContain('Helly');
      expect(options).toContain('Manager');
      expect(options).not.toContain('Vishva');
      expect(options).not.toContain('Mike');
    });
  });

  test.describe('Rep Helly (PIN 7721)', () => {
    test.beforeEach(async ({ page }) => {
      await loginAs(page, HELLY);
    });

    test('Sees only her own leads', async ({ page }) => {
      await expect(page.locator(LEAD_CARD).first()).toBeVisible();
      const tags = await page.locator(REP_TAG).allTextContents();
      expect(tags.length).toBeGreaterThan(0);
      for (const t of tags) {
        expect(t).toContain('Helly');
      }
    });

    test('Does NOT see Team nav link', async ({ page }) => {
      await expect(page.locator('a[href="/dashboard/team"]')).toHaveCount(0);
    });

    test('Does NOT see Settings nav link', async ({ page }) => {
      await expect(page.locator('a[href="/dashboard/settings"]')).toHaveCount(0);
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

    test('New Lead is assigned to self', async ({ page }) => {
      await createLead(page, 'Helly New Lead', '+17781110008');
      // Every visible lead should still be Helly's (the new one included).
      const tags = await page.locator(REP_TAG).allTextContents();
      for (const t of tags) {
        expect(t).toContain('Helly');
      }
    });

    test('Logout works', async ({ page }) => {
      await logout(page);
    });
  });
});
