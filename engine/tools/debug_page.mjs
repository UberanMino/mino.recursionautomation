// Load a built project in headless Chrome, print console errors, screenshot at time t.
import puppeteer from "puppeteer-core";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
const [dir, t = "0.5", out = "/tmp/dbg.png"] = process.argv.slice(2);
const types = { ".html": "text/html", ".js": "text/javascript", ".woff2": "font/woff2", ".json": "application/json" };
const srv = http.createServer((q, s) => {
  const p = path.join(dir, decodeURIComponent(q.url.split("?")[0]) === "/" ? "index.html" : decodeURIComponent(q.url.split("?")[0]));
  fs.readFile(p, (e, d) => { if (e) { s.writeHead(404); s.end(); return; } s.writeHead(200, { "content-type": types[path.extname(p)] || "application/octet-stream" }); s.end(d); });
}).listen(0);
const port = srv.address().port;
const browser = await puppeteer.launch({ executablePath: process.env.HYPERFRAMES_BROWSER_PATH || "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1080, height: 1920 });
page.on("console", (m) => console.log("[console]", m.type(), m.text().slice(0, 3000)));
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 3000)));
await page.evaluateOnNewDocument(() => { window.__timelines = {}; });
await page.goto(`http://localhost:${port}/`, { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 800));
const info = await page.evaluate((tt) => { if (window.__mrRender) { window.__mrRender(parseFloat(tt)); return "rendered"; } return "no renderer"; }, t);
console.log(info);
await page.screenshot({ path: out });
await browser.close(); srv.close();
