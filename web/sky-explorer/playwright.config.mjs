import {defineConfig} from '@playwright/test';
import {existsSync} from 'node:fs';
export default defineConfig({
 testDir:'./tests/browser',timeout:45000,
 use:{baseURL:'http://localhost:4173',launchOptions:{...(existsSync('/opt/google/chrome/chrome')?{executablePath:'/opt/google/chrome/chrome'}:{}),args:['--no-sandbox','--enable-unsafe-swiftshader']}},
 webServer:{command:'npm run build && npm run dev',url:'http://localhost:4173/health',reuseExistingServer:true},
});
