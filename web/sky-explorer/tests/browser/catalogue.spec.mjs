import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('zephyr-lab-tour-v1','test'));});
const observed=readFileSync(new URL('../fixtures/spherex_cutout.fits',import.meta.url));
test('no sampling by default; complete catalogue paginates and opens images outside the loaded detector',async({page})=>{
 let cutouts=0;const collections=[];
 await page.route('**/api/archive?**',route=>{
  const collection=new URL(route.request().url()).searchParams.get('collection');collections.push(collection);
  const rows=Array.from({length:265},(_,i)=>`${60800+i/100},SPHEREx-D${i%2?3:6},obs_${i},https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/test/${i}.fits`);
  route.fulfill({contentType:'text/csv',body:'t_min,energy_bandpassname,obs_id,access_url\n'+(collection==='spherex_dr1'?rows.join('\n'):'')});
 });
 await page.route('**/api/cutout?**',route=>{cutouts++;return route.fulfill({contentType:'application/fits',body:observed});});
 await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 await expect(page.locator('#limit')).toHaveValue('all');await expect(page.locator('#collection')).toHaveValue('all');
 await page.locator('#search-button').click();await expect(page.locator('#search-button')).toBeEnabled({timeout:40000});
 expect(collections).toEqual(['spherex_dr1','spherex_qr3','spherex_dr1_deep','spherex_qr3_deep']);expect(cutouts).toBe(133);await expect(page.locator('#status')).toContainText('133/133');
 await expect(page.locator('#catalogue-count')).toContainText('265 listed files');await expect(page.locator('#catalogue-body tr')).toHaveCount(50);
 await page.locator('#catalogue-next').click();await expect(page.locator('#catalogue-page')).toHaveText('Page 2 of 6');
 await page.locator('#catalogue-detector').selectOption('SPHEREx-D3');await expect(page.locator('#catalogue-count')).toContainText('132 images');
 await page.locator('#catalogue-search').fill('obs_263');await expect(page.locator('#catalogue-body tr')).toHaveCount(1);
 await page.locator('[data-mode="difference"]').click();await page.locator('#catalogue-body button').click();await expect(page.locator('#target-title')).toHaveText('obs_263');expect(cutouts).toBe(134);await expect(page.locator('[data-mode="image"]')).toHaveClass('active');
 const csv=page.waitForEvent('download');await page.locator('#catalogue-export').click();expect((await csv).suggestedFilename()).toBe('spherex-all-images.csv');
});
test('individual exposure animation keeps every loaded image accessible',async({page})=>{
 await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 await page.locator('#group').selectOption('individual');await expect(page.locator('#frame-label')).toHaveText('1 / 12');
 await page.locator('#frame').fill('11');await page.locator('#frame').dispatchEvent('input');await expect(page.locator('#frame-label')).toHaveText('12 / 12');
});
