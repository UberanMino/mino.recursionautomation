/* mino.recursion runtime — renders one edit plan, frame-exact from HyperFrames time.
 * Everything visible is a pure function of t: the GSAP timeline is only the clock,
 * hf-seek (if dispatched) and the tween's onUpdate both call render(t). */
(function () {
  "use strict";
  const PLAN = window.__PLAN__;
  const W = PLAN.width, H = PLAN.height, FPS = PLAN.fps, D = PLAN.duration;
  const SS = PLAN.render.sceneScale || 1;
  const SW = Math.round(W * SS), SH = Math.round(H * SS);

  // ---------- seeded helpers ----------
  function hash(n) { const x = Math.sin(n * 127.1 + PLAN.seed * 311.7) * 43758.5453; return x - Math.floor(x); }
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const ease = {
    outExpo: (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    outBack: (p) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
    inOut: (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2),
    outQuad: (p) => 1 - (1 - p) * (1 - p),
  };

  // ---------- audio / beat lookup ----------
  const A = PLAN.audio;
  const beats = PLAN.beats, downbeats = PLAN.downbeats;
  function lastIndex(arr, t) { let lo = 0, hi = arr.length - 1, r = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m] <= t + 1e-6) { r = m; lo = m + 1; } else hi = m - 1; } return r; }
  function beatState(t) {
    const i = lastIndex(beats, t);
    if (i < 0) { const per = 60 / PLAN.song.bpm; const first = beats.length ? beats[0] : 0; return { idx: -1, beat: (t - first) / per, since: 9, lastT: -9 }; }
    const per = i + 1 < beats.length ? beats[i + 1] - beats[i] : 60 / PLAN.song.bpm;
    return { idx: i, beat: i + (t - beats[i]) / per, since: t - beats[i], lastT: beats[i] };
  }
  function sinceDownbeat(t) { const i = lastIndex(downbeats, t); return i < 0 ? 9 : t - downbeats[i]; }
  function feat(name, f) { const a = A[name]; return a && a.length ? a[clamp(f, 0, a.length - 1)] : 0; }

  // ---------- GL setup ----------
  const cv = document.getElementById("gl");
  cv.width = W; cv.height = H;
  const gl = cv.getContext("webgl2", { preserveDrawingBuffer: true, antialias: false, premultipliedAlpha: false, alpha: false });
  if (!gl) throw new Error("WebGL2 unavailable");
  const VS = `#version 300 es
in vec2 aP; out vec2 vUV; void main(){ vUV=aP*0.5+0.5; gl_Position=vec4(aP,0.0,1.0); }`;
  function compile(type, src) {
    const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) + "\n" + src.split("\n").map((l, i) => i + 1 + ": " + l).join("\n"));
    return s;
  }
  function program(fs, defines) {
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, VS));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, "#version 300 es\n" + (defines || "") + fs));
    gl.bindAttribLocation(p, 0, "aP"); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const u = {}; const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const info = gl.getActiveUniform(p, i); u[info.name] = gl.getUniformLocation(p, info.name); }
    return { p, u };
  }
  const SCENE_PROGS = {};
  function sceneProgram(id, lib) {
    const k = (lib || "scenes") + ":" + id;
    if (!SCENE_PROGS[k]) SCENE_PROGS[k] = program(window.__SHADERS__[lib || "scenes"], `#define SCENE ${id}\n`);
    return SCENE_PROGS[k];
  }
  // compile every scene this plan uses up front, so the first captured frame is not a compile stall
  for (const s of PLAN.segments) sceneProgram(s.scene, s.lib);
  const COMP_PROGS = {};
  function compProgram(tt) {
    const k = tt == null ? "none" : String(tt);
    if (!COMP_PROGS[k]) COMP_PROGS[k] = program(window.__SHADERS__.composite, tt == null ? "" : `#define TT ${tt}\n`);
    return COMP_PROGS[k];
  }
  compProgram(null);
  for (const tr of PLAN.transitions) compProgram(tr.type);
  const vbo = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

  function makeTarget(w, h) {
    const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fb = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return { tex, fb, w, h };
  }
  const TA = makeTarget(SW, SH), TB = makeTarget(SW, SH);
  const ovTex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, ovTex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

  // ---------- overlay (2D) ----------
  const ov = document.createElement("canvas"); ov.width = W; ov.height = H;
  const ctx = ov.getContext("2d");

  function seg(t) { const s = PLAN.segments; for (let i = s.length - 1; i >= 0; i--) if (t >= s[i].t0 - 1e-6) return i; return 0; }
  function activeTransition(t) {
    for (const tr of PLAN.transitions) { const a = tr.t - tr.dur / 2, b = tr.t + tr.dur / 2; if (t >= a && t < b) return { tr, p: (t - a) / tr.dur }; }
    return null;
  }
  // frame-level flicker (line style): invert / hue / mirror tiles / time stutter, one state per 16th note
  const FL = (PLAN.post && PLAN.post.flicker) || [];
  function flickerAt(t) { let lo = 0, hi = FL.length - 1, r = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (FL[m][0] <= t + 1e-6) { r = m; lo = m + 1; } else hi = m - 1; } return r < 0 ? null : FL[r]; }
  function inWindows(list, t) { for (const w of list || []) if (t >= w[0] && t < w[1]) return w; return null; }

  function drawScene(target, s, t, au0, bs0) {
    // a "still" segment ignores the music completely (used for the motion-aftereffect reveal)
    const au = s.still ? { bass: 0, onset: 0, high: 0, rms: 0, kickEnv: 0 } : au0;
    const bs = s.still ? { beat: 0 } : bs0;
    gl.bindFramebuffer(gl.FRAMEBUFFER, target.fb); gl.viewport(0, 0, target.w, target.h);
    const SP = sceneProgram(s.scene, s.lib); gl.useProgram(SP.p); const u = SP.u;
    const fk = flickerAt(t);
    const lt = (t - s.t0) * (s.speed == null ? 1 : s.speed) + (s.offset || 0) + (fk && !s.still ? fk[4] : 0);
    gl.uniform2f(u.uRes, target.w, target.h);
    gl.uniform1f(u.uT, lt);
    gl.uniform1i(u.uPal, s.pal);
    gl.uniform4f(u.uPrm, s.prm[0], s.prm[1], s.prm[2], s.prm[3]);
    gl.uniform1f(u.uSeed, (PLAN.seed % 97) * 0.731 + (s.seed || 0));
    const zp = s.zoomPulse || 0;
    gl.uniform1f(u.uZoom, (s.zoom || 1) * (1 + zp * au.kickEnv) * Math.pow(1 + (s.zoomDrift || 0), lt));
    gl.uniform1f(u.uRot, (s.rot || 0) + (s.spin || 0) * lt);
    gl.uniform1f(u.uBass, au.bass); gl.uniform1f(u.uKick, au.kickEnv); gl.uniform1f(u.uOnset, au.onset);
    gl.uniform1f(u.uHigh, au.high); gl.uniform1f(u.uRms, au.rms);
    gl.uniform1f(u.uBeat, Math.max(0, bs.beat)); gl.uniform1f(u.uEnergy, s.energy || 0.5);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  // ---- overlay painters ----
  function fontStr(st, size) { return `${size}px "${st.font || "Anton"}"`; }
  function fitSize(text, st, maxW) {
    let size = st.size || 150; ctx.font = fontStr(st, size);
    const lines = String(text).split("\n");
    let w = Math.max(...lines.map((l) => ctx.measureText(l).width));
    if (w > maxW) size = Math.floor(size * maxW / w);
    return size;
  }
  function paintText(text, x, y, st, size, alpha) {
    ctx.save(); ctx.globalAlpha = alpha; ctx.font = fontStr(st, size);
    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
    const lines = String(text).split("\n"); const lh = size * (st.lineHeight || 1.02);
    lines.forEach((ln, i) => {
      const yy = y + (i - (lines.length - 1) / 2) * lh;
      const ex = st.extrude || 0;
      for (let k = ex; k > 0; k--) { // 3D extrude in alternating palette colours
        ctx.fillStyle = (st.extrudeColors || ["#000"])[k % (st.extrudeColors || ["#000"]).length];
        ctx.fillText(ln, x + k * 2.2, yy + k * 2.2);
      }
      if (st.stroke) { ctx.strokeStyle = st.stroke; ctx.lineWidth = st.strokeW || size * 0.09; ctx.strokeText(ln, x, yy); }
      if (st.gradient) {
        const g = ctx.createLinearGradient(x - size * 2, yy - size / 2, x + size * 2, yy + size / 2);
        st.gradient.forEach((c, j) => g.addColorStop(j / (st.gradient.length - 1), c));
        ctx.fillStyle = g;
      } else ctx.fillStyle = st.color || "#fff";
      ctx.fillText(ln, x, yy);
    });
    ctx.restore();
  }
  function glitchText(text, x, y, st, size, alpha, f, amt) {
    // RGB ghost copies + sliced offsets
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    const off = size * 0.06 * amt;
    paintText(text, x - off, y, { ...st, color: "#ff0040", gradient: null, extrude: 0, stroke: null }, size, alpha * 0.8);
    paintText(text, x + off, y, { ...st, color: "#00e5ff", gradient: null, extrude: 0, stroke: null }, size, alpha * 0.8);
    ctx.restore();
    const slices = 7; const lines = String(text).split("\n").length; const hgt = size * 1.1 * lines;
    for (let i = 0; i < slices; i++) {
      const y0 = y - hgt / 2 + (hgt / slices) * i;
      const dx = (hash(f * 13 + i * 7) - 0.5) * size * 0.5 * amt * (hash(f + i) > 0.6 ? 1 : 0);
      ctx.save(); ctx.beginPath(); ctx.rect(0, y0, W, hgt / slices + 1); ctx.clip();
      paintText(text, x + dx, y, st, size, alpha); ctx.restore();
    }
  }
  function win98(x, y, w, title, msg, scale, alpha, noIcon) {
    ctx.save(); ctx.globalAlpha = alpha; ctx.translate(x, y); ctx.scale(scale, scale);
    const h = 230;
    ctx.fillStyle = "#000"; ctx.fillRect(6, 6, w, h); // drop shadow
    ctx.fillStyle = "#c0c0c0"; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, 3); ctx.fillRect(0, 0, 3, h);
    ctx.fillStyle = "#404040"; ctx.fillRect(0, h - 3, w, 3); ctx.fillRect(w - 3, 0, 3, h);
    const g = ctx.createLinearGradient(0, 0, w, 0); g.addColorStop(0, "#000080"); g.addColorStop(1, "#1084d0");
    ctx.fillStyle = g; ctx.fillRect(6, 6, w - 12, 44);
    ctx.fillStyle = "#fff"; ctx.font = '34px "VT323"'; ctx.textBaseline = "middle"; ctx.textAlign = "left";
    ctx.fillText(title, 18, 29);
    // close box
    ctx.fillStyle = "#c0c0c0"; ctx.fillRect(w - 50, 12, 36, 32); ctx.fillStyle = "#000"; ctx.font = '30px "VT323"'; ctx.fillText("x", w - 39, 28);
    if (!noIcon) {
    // error icon
    ctx.fillStyle = "#e00000"; ctx.beginPath(); ctx.arc(62, 112, 34, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 9; ctx.beginPath(); ctx.moveTo(48, 98); ctx.lineTo(76, 126); ctx.moveTo(76, 98); ctx.lineTo(48, 126); ctx.stroke();
    ctx.fillStyle = "#000"; ctx.font = '38px "VT323"';
    const words = msg.split(" "); let line = "", ly = 96;
    for (const wd of words) { const tt = line ? line + " " + wd : wd; if (ctx.measureText(tt).width > w - 150) { ctx.fillText(line, 120, ly); line = wd; ly += 36; } else line = tt; }
    ctx.fillText(line, 120, ly);
    }
    if (noIcon) { ctx.restore(); return; } // progress window: no OK button
    // OK button
    ctx.fillStyle = "#c0c0c0"; ctx.fillRect(w / 2 - 70, h - 64, 140, 46);
    ctx.fillStyle = "#fff"; ctx.fillRect(w / 2 - 70, h - 64, 140, 3); ctx.fillRect(w / 2 - 70, h - 64, 3, 46);
    ctx.fillStyle = "#404040"; ctx.fillRect(w / 2 - 70, h - 21, 140, 3); ctx.fillRect(w / 2 + 67, h - 64, 3, 46);
    ctx.fillStyle = "#000"; ctx.textAlign = "center"; ctx.fillText("OK", w / 2, h - 41);
    ctx.restore();
  }
  function progressBar(x, y, w, label, pct, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    win98(x, y, w, label.title || "loading.exe", "", 1, 1, true);
    const bx = x + 30, by = y + 150, bw = w - 60;
    ctx.fillStyle = "#fff"; ctx.fillRect(bx, by, bw, 36); ctx.strokeStyle = "#404040"; ctx.lineWidth = 3; ctx.strokeRect(bx, by, bw, 36);
    const n = Math.floor((bw - 8) / 22), filled = Math.floor(n * pct);
    ctx.fillStyle = "#000080"; for (let i = 0; i < filled; i++) ctx.fillRect(bx + 4 + i * 22, by + 4, 18, 28);
    ctx.fillStyle = "#000"; ctx.font = '38px "VT323"'; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(label.text + " " + Math.floor(pct * 100) + "%", x + 30, y + 100);
    ctx.restore();
  }

  let bands = [];
  function band(y0, y1) { bands.push([Math.max(0, y0), Math.min(H, y1)]); }
  function packBands() {
    // merge to at most 4 bands, convert to flipped uv
    bands.sort((a, b) => a[0] - b[0]);
    const m = [];
    for (const b of bands) { if (m.length && b[0] <= m[m.length - 1][1] + 40) m[m.length - 1][1] = Math.max(m[m.length - 1][1], b[1]); else m.push([b[0], b[1]]); }
    while (m.length > 4) { let bi = 0, bg = 1e9; for (let i = 0; i < m.length - 1; i++) { const g = m[i + 1][0] - m[i][1]; if (g < bg) { bg = g; bi = i; } } m[bi][1] = m[bi + 1][1]; m.splice(bi + 1, 1); }
    const uv = []; for (let i = 0; i < 4; i++) { const b = m[i]; if (b) uv.push(1 - b[1] / H, 1 - b[0] / H); else uv.push(2, 2); }
    return uv;
  }
  function drawOverlay(t, f, bs, au) {
    ctx.clearRect(0, 0, W, H);
    bands = [];
    for (const o of PLAN.overlays) {
      if (o.kind !== "watermark" && (t < o.t0 || t >= o.t1)) continue;
      const lt = t - (o.t0 || 0), len = (o.t1 || D) - (o.t0 || 0);
      const outA = o.fadeOut === false ? 1 : clamp((len - lt) / 0.12, 0, 1);
      const st = o.style || {};
      if (o.kind === "hook" || o.kind === "caption") {
        const maxW = W * (o.maxW || 0.86);
        const size = fitSize(o.text, st, maxW);
        let sc = 1, a = outA, y = H * (o.y || 0.42);
        if (o.anim === "punch") { const p = clamp(lt / 0.35, 0, 1); sc = 1.9 - 0.9 * ease.outExpo(p); a *= clamp(lt / 0.06, 0, 1); }
        if (o.anim === "rise") { const p = clamp(lt / 0.5, 0, 1); y += (1 - ease.outBack(p)) * 120; a *= p; }
        sc *= 1 + (o.beatBounce || 0) * au.kickEnv;
        const nl = String(o.text).split("\n").length;
        band(y - (nl * size * 0.62 + 40) * sc - 30, y + (nl * size * 0.62 + 40) * sc + 30);
        ctx.save(); ctx.translate(W / 2, y); ctx.scale(sc, sc); ctx.rotate((o.tilt || 0) * Math.PI / 180);
        if (o.glitch && (hash(f * 3.1) < o.glitch || lt < 0.15)) glitchText(o.text, 0, 0, st, size, a, f, 1);
        else paintText(o.text, 0, 0, st, size, a);
        ctx.restore();
      } else if (o.kind === "type") { // typewriter, one char per step
        const n = Math.min(o.text.length, Math.floor(lt * (o.cps || 18)));
        const shown = o.text.slice(0, n) + (Math.floor(lt * 3) % 2 ? "_" : " ");
        const size = fitSize(o.text + "_", st, W * (o.maxW || 0.86));
        band(H * (o.y || 0.42) - size, H * (o.y || 0.42) + size);
        paintText(shown, W / 2, H * (o.y || 0.42), st, size, outA);
      } else if (o.kind === "words") { // one word per beat, punching in
        const times = o.times; let k = lastIndex(times, t); if (k < 0) continue;
        const word = o.words[Math.min(k, o.words.length - 1)];
        const p = clamp((t - times[k]) / 0.25, 0, 1);
        const size = fitSize(word, st, W * (o.maxW || 0.9));
        band(H * (o.y || 0.42) - size * 1.1, H * (o.y || 0.42) + size * 1.1);
        ctx.save(); ctx.translate(W / 2, H * (o.y || 0.42)); const sc = 1.6 - 0.6 * ease.outExpo(p); ctx.scale(sc, sc);
        if (o.glitch) glitchText(word, 0, 0, st, size, outA, f, 1 - p); else paintText(word, 0, 0, st, size, outA);
        ctx.restore();
      } else if (o.kind === "popups") { // Win98 error cascade, one window per spawn time
        const k = lastIndex(o.times, t);
        for (let i = 0; i <= k; i++) {
          const age = t - o.times[i];
          const sc = 0.6 + 0.4 * ease.outBack(clamp(age / 0.18, 0, 1));
          const px = o.x != null ? o.x + i * 34 : 70 + hash(i * 9.7 + 1) * (W - 860);
          const py = o.y != null ? o.y + i * 34 : 300 + hash(i * 4.3 + 2) * (H - 900);
          band(py - 10, py + 250);
          win98(px, py, 720, o.titles[i % o.titles.length], o.msgs[i % o.msgs.length], sc, outA);
        }
      } else if (o.kind === "progress") {
        const p = clamp(lt / len, 0, 1); const pct = o.from + (o.to - o.from) * ease.inOut(p);
        band(H * (o.y || 0.4) - 10, H * (o.y || 0.4) + 250);
        progressBar(W / 2 - 360, H * (o.y || 0.4), 720, { title: o.title, text: o.text }, pct, outA);
      } else if (o.kind === "countdown") {
        const n = Math.max(0, Math.ceil(o.from - lt));
        band(H * (o.y || 0.5) - (st.size || 260) * 0.7, H * (o.y || 0.5) + (st.size || 260) * 0.7);
        paintText(String(n), W / 2, H * (o.y || 0.5), st, st.size || 260, outA * 0.95);
      } else if (o.kind === "dot") {
        band(H / 2 - 40, H / 2 + 40);
        ctx.save(); ctx.globalAlpha = outA; ctx.fillStyle = o.color || "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = 6;
        ctx.beginPath(); ctx.arc(W / 2, H / 2, (o.r || 16) + 10, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill(); ctx.stroke();
        ctx.beginPath(); ctx.arc(W / 2, H / 2, o.r || 16, 0, Math.PI * 2); ctx.fillStyle = o.color || "#ff2bd6"; ctx.fill(); ctx.restore();
      } else if (o.kind === "watermark") {
        band(H * (o.y || 0.135) - (o.size || 40), H * (o.y || 0.135) + (o.size || 40));
        ctx.save(); ctx.globalAlpha = o.alpha || 0.9; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.font = `${o.size || 40}px "VT323"`; ctx.lineWidth = 6; ctx.strokeStyle = "rgba(0,0,0,0.8)";
        ctx.strokeText(o.text, W / 2, H * (o.y || 0.135)); ctx.fillStyle = "#fff"; ctx.fillText(o.text, W / 2, H * (o.y || 0.135));
        ctx.restore();
      }
    }
    gl.bindTexture(gl.TEXTURE_2D, ovTex);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, ov);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  }

  let lastT = -1;
  function render(t) {
    t = clamp(t, 0, D - 1e-4);
    if (Math.abs(t - lastT) < 1e-6) return;
    lastT = t;
    const f = Math.round(t * FPS);
    const bs = beatState(t);
    const P = PLAN.post;
    const kickEnv = Math.exp(-bs.since * (P.punchDecay || 9));
    const au = { bass: feat("bass", f), onset: feat("onset", f), high: feat("high", f), rms: feat("rms", f), kickEnv };
    const si = seg(t), s = PLAN.segments[si];
    const at = activeTransition(t);
    const PERF0 = window.__mrPerf; let p0 = 0; if (PERF0) { gl.finish(); p0 = performance.now(); }
    if (at) {
      const k = PLAN.segments.findIndex((x) => Math.abs(x.t0 - at.tr.t) < 1e-4);
      const sa = PLAN.segments[Math.max(0, k - 1)], sb = PLAN.segments[k];
      drawScene(TA, sa, t, au, bs); drawScene(TB, sb, t, au, bs);
    } else drawScene(TA, s, t, au, bs);
    const PERF = window.__mrPerf; let pt = 0;
    if (PERF) { const px = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); pt = performance.now(); PERF.scene = (PERF.scene || 0) + pt - p0; }
    drawOverlay(t, f, bs, au);
    if (PERF) { gl.finish(); PERF.overlay += performance.now() - pt; pt = performance.now(); }

    gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, W, H);
    const CP = compProgram(at ? at.tr.type : null); gl.useProgram(CP.p); const u = CP.u;
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, TA.tex); gl.uniform1i(u.uA, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, TB.tex); gl.uniform1i(u.uB, 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, ovTex); gl.uniform1i(u.uOv, 2);
    gl.uniform2f(u.uRes, W, H);
    gl.uniform1f(u.uP, at ? at.p : -1);
    gl.uniform1f(u.uSeed, (PLAN.seed % 53) * 0.37); gl.uniform1f(u.uFrame, f); gl.uniform1f(u.uTime, t);
    const energy = s.still ? 0 : (s.energy || 0.5);
    gl.uniform1f(u.uPunch, s.still ? 0 : (P.punch || 0.05) * kickEnv * (0.4 + energy));
    gl.uniform1f(u.uRGB, (P.rgbBase || 0.002) + (P.rgbBeat || 0.008) * kickEnv * energy + (P.rgbOnset || 0.004) * au.onset);
    const sd = sinceDownbeat(t); const shakeA = (P.shake || 0) * Math.exp(-sd * 12) * energy;
    gl.uniform2f(u.uShake, (hash(f * 1.3) - 0.5) * shakeA, (hash(f * 2.7) - 0.5) * shakeA);
    const fk = flickerAt(t);
    const inv = inWindows(P.inverts, t); gl.uniform1f(u.uInvert, (inv ? 1 : 0) ^ (fk ? fk[1] : 0));
    let flash = 0, fc = [1, 1, 1];
    for (const fl of P.flashes || []) { const d = t - fl.t; if (d >= 0 && d < fl.dur) { flash = Math.max(flash, (1 - d / fl.dur) * (fl.amt || 0.6)); fc = fl.color; } }
    gl.uniform1f(u.uFlash, flash); gl.uniform3f(u.uFlashCol, fc[0], fc[1], fc[2]);
    gl.uniform1f(u.uGrain, P.grain || 0.04); gl.uniform1f(u.uScan, P.scan || 0); gl.uniform1f(u.uVig, P.vignette || 0.35);
    gl.uniform1f(u.uHue, (s.hue || 0) + (P.hueSpeed || 0) * t + (fk ? fk[2] : 0));
    gl.uniform1f(u.uBloom, (P.bloom || 0) * (1 + (P.bloomPulse || 0) * kickEnv));
    const gw = inWindows(P.glitches, t); gl.uniform1f(u.uGlitch, gw ? (gw[2] || 1) : 0);
    gl.uniform1f(u.uBarrel, P.barrel || 0);
    const pw = inWindows(P.pixelate, t); gl.uniform1f(u.uPixel, pw ? pw[2] : 0);
    gl.uniform1i(u.uMirror, fk && fk[3] ? fk[3] : (s.mirror || 0));
    gl.uniform1f(u.uOvFx, P.overlayFx == null ? 0.35 : P.overlayFx);
    const ob = packBands(); gl.uniform4f(u.uOvBands0, ob[0], ob[1], ob[2], ob[3]); gl.uniform4f(u.uOvBands1, ob[4], ob[5], ob[6], ob[7]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (PERF) { const px = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); PERF.comp += performance.now() - pt; }
  }

  window.__mrRender = render;
  window.addEventListener("hf-seek", (e) => render(e.detail.time));

  const fonts = ["Anton", "Shrikhand", "VT323", "Rubik Mono One", "Monoton"];
  Promise.all(fonts.map((n) => document.fonts.load(`40px "${n}"`))).then(() => {
    const clock = { t: 0 };
    const tl = gsap.timeline({ paused: true });
    tl.to(clock, { t: D, duration: D, ease: "none", onUpdate: () => render(clock.t) }, 0);
    lastT = -1; render(0);
    window.__timelines["main"] = tl;
    if (window.__hfForceTimelineRebind) window.__hfForceTimelineRebind();
  });
})();
