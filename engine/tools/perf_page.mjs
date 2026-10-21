// Time render(t) per frame for a built project (forces GPU sync with readPixels).
import puppeteer from "puppeteer-core";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
const [dir, n = "20"] = process.argv.slice(2);
const types = { ".html": "text/html", ".js": "text/javascript", ".woff2": "font/woff2" };
const srv = http.createServer((q, s) => { const u = decodeURIComponent(q.url.split("?")[0]); const p = path.join(dir, u === "/" ? "index.html" : u);
  fs.readFile(p, (e, d) => { if (e) { s.writeHead(404); s.end(); return; } s.writeHead(200, { "content-type": types[path.extname(p)] || "application/octet-stream" }); s.end(d); }); }).listen(0);
const browser = await puppeteer.launch({ executablePath: "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"] });
const page = await browser.newPage(); await page.setViewport({ width: 1080, height: 1920 });
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 2000)));
await page.evaluateOnNewDocument(() => { window.__timelines = {}; window.__mrPerf = { overlay: 0, comp: 0 }; });
const t0 = Date.now();
await page.goto(`http://localhost:${srv.address().port}/`, { waitUntil: "networkidle0" });
console.log("load ms", Date.now() - t0);
const res = await page.evaluate((N) => {
  const P = window.__PLAN__; const gl = document.getElementById("gl").getContext("webgl2"); const px = new Uint8Array(4);
  const out = [];
  for (let i = 0; i < N; i++) { const t = (i + 0.5) * P.duration / N; const a = performance.now(); window.__mrRender(t); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); out.push([t.toFixed(2), Math.round(performance.now() - a)]); }
  return out;
}, parseInt(n));
console.log(JSON.stringify(res)); console.log("perf", JSON.stringify(await page.evaluate(() => window.__mrPerf))); console.log("avg ms", res.reduce((a, b) => a + b[1], 0) / res.length);
await browser.close(); srv.close();
