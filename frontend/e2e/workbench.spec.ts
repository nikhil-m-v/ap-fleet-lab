import {test,expect} from '@playwright/test';

test('run, pause, disrupt, resume, compare, and replay',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('canvas')).toBeVisible();
  await page.getByLabel('Scheduling strategy').selectOption('fcfs');
  await page.getByLabel('Measure, seconds').fill('20');
  await page.getByRole('button',{name:'Run experiment →'}).click();
  await expect(page.locator('.status')).toHaveText('RUNNING',{timeout:15000});
  await page.getByRole('button',{name:'Pause',exact:true}).click();
  await expect(page.locator('.status')).toHaveText('PAUSED');
  const pausedClock=await page.locator('.clock').innerText();
  await page.waitForTimeout(350);
  expect(await page.locator('.clock').innerText()).toBe(pausedClock);
  await page.getByRole('button',{name:'Inject 3s stop'}).click();
  await page.getByRole('button',{name:'Resume',exact:true}).click();
  await expect(page.locator('.status')).toHaveText('COMPLETED',{timeout:15000});
  await page.getByRole('button',{name:/Compare runs/}).click();
  await expect(page.locator('tbody tr').first()).toContainText('completed');
  await page.getByRole('button',{name:'Replay',exact:true}).first().click();
  await expect(page.locator('.status')).toHaveText('REPLAY');
  await page.getByRole('slider',{name:'Replay frame'}).fill('5');
  await expect(page.getByRole('button',{name:'Play replay'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('mobile setup remains usable',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Run experiment →'})).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  expect(overflow).toBe(false);
});
