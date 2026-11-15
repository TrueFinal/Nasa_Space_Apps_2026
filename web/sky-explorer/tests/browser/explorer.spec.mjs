import {test,expect} from '@playwright/test';

test('five real targets animate, stack, subtract, measure and export',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 for(const [id,name,count] of [['barnard','Barnard’s Star',10],['epsilon','Epsilon Indi B',15],['wise0855','WISE 0855',12],['rwaur','RW Aurigae',6],['rdra','R Draconis',9]]){
  await page.locator(`[data-id="${id}"]`).click();
  await expect(page.locator('#target-title')).toHaveText(name);
  await expect(page.locator('#frame-label')).toContainText(` / ${count}`);
  const first=await page.locator('#frame-label').textContent();
  await expect(page.locator('#frame-label')).not.toHaveText(first);
  await page.locator('#by-frame').click();
  await page.locator('#stack-count').fill('3');await page.locator('#apply-stack').click();
  await expect(page.locator('[data-mode="trail"]')).toHaveClass(/active/);
  await page.locator('[data-mode="difference"]').click();
  await page.locator('#sky').click();await expect(page.locator('#spectrum-note')).toContainText('aperture measurements');
  await page.locator('[data-mode="image"]').click();
  const gif=page.waitForEvent('download');await page.locator('#gif').click();expect((await gif).suggestedFilename()).toBe('spherex-temporal.gif');
 }
 await expect(page.locator('#palette')).toHaveValue('gray');await expect(page.locator('#invert')).toBeChecked();
 const csv=page.waitForEvent('download');await page.locator('#export-spectrum').click();expect((await csv).suggestedFilename()).toBe('spherex-spectrum.csv');
 expect(errors).toEqual([]);
});

test('mobile layout and navigation fit, invalid coordinates are explained',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#nav-toggle').click();await expect(page.locator('#navigation')).toBeVisible();
 await page.locator('#ra').fill('999');await page.locator('#search-button').click();await expect(page.locator('#status')).toContainText('0–360');
});

test('coordinate URL includes dates and live search forwards filters without replacing prior data',async({page})=>{
 await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 let queried;
 await page.route('**/api/archive?**',async route=>{
  queried=new URL(route.request().url());
  await route.fulfill({status:200,contentType:'text/csv',body:'obs_id,access_url,energy_bandpassname,t_min\n'});
 });
 await page.locator('#ra').fill('08h55m10.831s');await page.locator('#dec').fill('-07:14:42.53');
 await page.locator('#start').fill('2025-05-01');await page.locator('#end').fill('2026-05-31');
 await page.locator('#collection').selectOption('spherex_dr1');
 await page.locator('#search-button').click();await expect(page.locator('#status')).toContainText('No exposures available');
 expect(Number(queried.searchParams.get('ra'))).toBeCloseTo(133.7951291667,8);
 expect(queried.searchParams.get('start')).toBe('2025-05-01');expect(queried.searchParams.get('end')).toBe('2026-05-31');
 await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
});

test('invalid coordinate links show an actionable message without crashing',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/?ra=999&dec=0');await expect(page.locator('#status')).toContainText('0–360');
 expect(errors).toEqual([]);
});
