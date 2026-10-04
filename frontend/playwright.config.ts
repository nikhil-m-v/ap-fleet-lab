import {defineConfig} from '@playwright/test';
import {existsSync} from 'node:fs';
const localPython=process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python';
const python=existsSync(localPython)?localPython:'python';
export default defineConfig({testDir:'./e2e',timeout:45000,workers:1,use:{baseURL:'http://127.0.0.1:8000',viewport:{width:1440,height:1100},headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})},webServer:{command:`${python} -m ap_fleet.cli serve`,url:'http://127.0.0.1:8000',reuseExistingServer:true,timeout:30000}});
