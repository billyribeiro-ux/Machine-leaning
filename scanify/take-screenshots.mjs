import { chromium } from '@playwright/test';
import { mkdirSync } from 'fs';

const BASE = 'http://localhost:5173';
const SCREENSHOT_DIR = '/home/user/Machine-leaning/scanify/screenshots';

const routes = [
  { path: '/', name: 'home' },
  { path: '/dashboard', name: 'dashboard' },
  { path: '/scanner', name: 'scanner' },
  { path: '/options', name: 'options' },
  { path: '/options/flow', name: 'options-flow' },
  { path: '/market', name: 'market' },
  { path: '/analysis', name: 'analysis' },
  { path: '/institutional', name: 'institutional' },
  { path: '/alerts', name: 'alerts' },
  { path: '/settings', name: 'settings' },
  { path: '/settings/appearance', name: 'settings-appearance' },
  { path: '/settings/vendors', name: 'settings-vendors' },
  { path: '/login', name: 'login' },
  { path: '/signup', name: 'signup' },
  { path: '/forgot-password', name: 'forgot-password' },
];

mkdirSync(SCREENSHOT_DIR, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: 'dark',
});

for (const route of routes) {
  const page = await context.newPage();
  try {
    console.log(`Navigating to ${route.path}...`);
    await page.goto(`${BASE}${route.path}`, { waitUntil: 'networkidle', timeout: 15000 });
    // Wait a bit for any animations/transitions
    await page.waitForTimeout(1000);
    const filePath = `${SCREENSHOT_DIR}/${route.name}.png`;
    await page.screenshot({ path: filePath, fullPage: true });
    console.log(`  -> Saved: ${filePath}`);
  } catch (err) {
    console.error(`  -> ERROR on ${route.path}: ${err.message}`);
  } finally {
    await page.close();
  }
}

await browser.close();
console.log('\nDone! All screenshots saved to:', SCREENSHOT_DIR);
