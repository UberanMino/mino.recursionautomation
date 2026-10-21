// mino.recursion scene library — one fragment shader, scene picked by uScene.
// Space: p.x in [-1,1], p.y in [-1.78,1.78] (portrait), y up.
precision highp float;
precision highp int;

uniform vec2 uRes;
uniform float uT;       // scene-local time (s), may be negative (loop closure)
// SCENE is injected as a compile-time #define: one small program per scene (SwiftShader-friendly)
uniform int uPal;
uniform vec4 uPrm;      // per-segment params, meaning depends on scene
uniform float uSeed;
uniform float uZoom;
uniform float uRot;
uniform float uBass, uKick, uOnset, uHigh, uRms;
uniform float uBeat;    // beats elapsed (fractional)
uniform float uEnergy;  // section intensity 0..1

out vec4 fragColor;

#define PI 3.14159265
#define TAU 6.28318531

// ---------- utils ----------
mat2 rot(float a){ float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }
float hash11(float n){ return fract(sin(n*127.1+uSeed*13.7)*43758.5453); }
float hash21(vec2 p){ p=fract(p*vec2(123.34,456.21)+uSeed*0.137); p+=dot(p,p+45.32); return fract(p.x*p.y); }
vec2 hash22(vec2 p){ float n=hash21(p); return vec2(n, hash21(p+n+17.0)); }
float noise(vec2 p){
  vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(hash21(i),hash21(i+vec2(1,0)),u.x), mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),u.x), u.y);
}
float fbm(vec2 p){ float v=0.0, a=0.5; for(int i=0;i<4;i++){ v+=a*noise(p); p=rot(0.6)*p*2.03+11.7; a*=0.5; } return v; }
float tri(float x){ return abs(fract(x)-0.5)*2.0; }
float beatEnv(){ return exp(-fract(uBeat)*6.0); }
vec3 hsv(float h,float s,float v){ vec3 k=clamp(abs(mod(h*6.0+vec3(0,4,2),6.0)-3.0)-1.0,0.0,1.0); return v*mix(vec3(1),k,s); }

// ---------- palettes (4 stops, cyclic) ----------
vec3 stop(int pal, int i){
  i = i - (i/4)*4;
  if(pal==0){ // hypno: purple / yellow / orange / deep violet
    if(i==0) return vec3(0.47,0.00,0.80); if(i==1) return vec3(1.00,0.80,0.00); if(i==2) return vec3(1.00,0.42,0.00); return vec3(0.22,0.00,0.42);
  } else if(pal==1){ // acid: pink / cyan / lime / electric blue
    if(i==0) return vec3(1.00,0.15,0.80); if(i==1) return vec3(0.00,0.92,1.00); if(i==2) return vec3(0.72,1.00,0.00); return vec3(0.16,0.12,1.00);
  } else if(pal==2){ // op-art: cream / black / rust / black
    if(i==0) return vec3(0.96,0.92,0.82); if(i==1) return vec3(0.04,0.04,0.05); if(i==2) return vec3(0.80,0.33,0.22); return vec3(0.04,0.04,0.05);
  } else if(pal==3){ // blood eyes: red / cream / teal / black
    if(i==0) return vec3(0.88,0.06,0.16); if(i==1) return vec3(0.98,0.92,0.84); if(i==2) return vec3(0.22,0.64,0.80); return vec3(0.07,0.02,0.03);
  } else if(pal==4){ // vapor y2k: sky / lilac / white / pink
    if(i==0) return vec3(0.45,0.76,1.00); if(i==1) return vec3(0.76,0.62,1.00); if(i==2) return vec3(0.98,0.98,1.00); return vec3(1.00,0.55,0.84);
  } else if(pal==5){ // rainbow
    return hsv(float(i)/4.0 + 0.03, 0.9, 1.0);
  } else if(pal==6){ // desert op: teal / salmon / cream / deep red
    if(i==0) return vec3(0.10,0.42,0.46); if(i==1) return vec3(0.96,0.55,0.42); if(i==2) return vec3(0.98,0.90,0.78); return vec3(0.62,0.10,0.14);
  } else { // toxic: black / neon green / magenta / yellow
    if(i==0) return vec3(0.02,0.02,0.03); if(i==1) return vec3(0.20,1.00,0.35); if(i==2) return vec3(1.00,0.00,0.78); return vec3(1.00,0.95,0.10);
  }
}
// smooth cyclic gradient
vec3 pal(float x){ x=fract(x)*4.0; int i=int(floor(x)); float f=smoothstep(0.0,1.0,fract(x)); return mix(stop(uPal,i),stop(uPal,i+1),f); }
// hard bands (op-art)
vec3 palHard(float x){ x=fract(x)*4.0; return stop(uPal,int(floor(x))); }
vec3 palHard3(float x){ x=fract(x)*3.0; return stop(uPal,int(floor(x))); }

// ---------- eye SDF helpers ----------
// almond: intersection of two circles; returns signed distance (neg inside)
float sdAlmond(vec2 q, float w, float h){
  // circle radius R placed so it passes through (+-w,0) and (0,h)
  float R=(w*w+h*h)/(2.0*h);
  float d1=length(q-vec2(0.0,h-R))-R;
  float d2=length(q-vec2(0.0,-(h-R)))-R;
  return max(d1,d2);
}
// draws an eye into col; q in eye space (eye width ~1), look = pupil offset, open 0..1, ph = per-eye seed
vec3 eye(vec3 col, vec2 q, vec2 look, float open, float ph, float spiralIris){
  float h=0.42*open+0.001;
  float d=sdAlmond(q,0.98,h);
  float aa=0.012;
  // skin crease shadow
  col=mix(col, col*0.35, smoothstep(0.08,0.0,d)*0.6);
  if(d<0.0){
    vec3 sclera=vec3(0.98,0.95,0.90);
    // veins
    float v=smoothstep(0.04,0.0,abs(noise(q*9.0+ph*9.0)-0.5))*smoothstep(0.15,0.75,length(q));
    sclera=mix(sclera,vec3(0.85,0.08,0.12),v*0.7);
    sclera*=0.75+0.25*smoothstep(-0.05,-0.30,d); // edge shading
    vec2 ip=q-look;
    float r=length(ip);
    float irisR=0.36;
    vec3 c=sclera;
    if(r<irisR){
      float a=atan(ip.y,ip.x);
      vec3 ic=pal(r*2.2+ph+uT*0.05);
      if(spiralIris>0.5){ ic=palHard3(a/TAU*3.0+log(r+0.02)*2.5-uT*2.0); }
      ic*=0.65+0.45*noise(vec2(a*12.0,r*30.0)); // fibres
      ic=mix(ic, ic*0.4, smoothstep(irisR-0.08,irisR,r)); // limbal ring
      float pupil=0.12+0.07*uBass;
      ic=mix(vec3(0.01), ic, smoothstep(pupil, pupil+aa, r));
      // highlight
      ic+=smoothstep(0.06,0.0,length(ip-vec2(-0.1,0.12)))*0.9;
      c=mix(c,ic,smoothstep(irisR,irisR-aa,r));
    }
    col=mix(col,c,smoothstep(0.0,-aa,d));
  }
  // lid line
  col=mix(col, vec3(0.02), smoothstep(aa*2.0,0.0,abs(d))*0.9);
  return col;
}

// ---------- scenes ----------
// 0 zigzag log spiral (ref: hypno spiral)
vec3 sSpiral(vec2 p){
  float r=length(p), a=atan(p.y,p.x);
  float arms=floor(uPrm.x+0.5); // 1..6
  float twist=uPrm.y;           // 2..6
  float zig=0.11*(tri(a/TAU*uPrm.z*2.0 + log(r)*1.2)-0.5)*uPrm.w;
  float s=a/TAU*arms + log(r+1e-4)*twist - uT*1.6 - uKick*0.15 + zig;
  float f=fract(s*3.0);
  vec3 c=palHard3(s);            // period 1 in s -> seamless across the atan cut
  c=mix(c, vec3(0.02), smoothstep(0.07,0.0,min(f,1.0-f))); // black outlines
  c*=smoothstep(0.0,0.05,r);
  return c;
}
// 1 op-art sunburst + central eye (ref: hands/eye collage)
vec3 sOpRadial(vec2 p){
  float r=length(p), a=atan(p.y,p.x);
  float rays=floor(uPrm.x+0.5);
  float w=0.12*sin(r*6.0-uT*2.5)+0.05*sin(a*5.0+uT);
  float s=fract(a/TAU*rays + w + uT*0.05);
  vec3 c=mix(stop(uPal,0),stop(uPal,1),step(0.5,s));
  // concentric pulse ring
  float ring=smoothstep(0.02,0.0,abs(fract(r*1.2-uT*0.6)-0.5)-0.47);
  c=mix(c,stop(uPal,2),ring*0.8);
  float es=uPrm.y; // eye scale
  if(es>0.01){
    vec2 q=p/es;
    vec2 look=0.18*vec2(sin(uT*1.3+uSeed), cos(uT*0.9))*vec2(1.0,0.5);
    float blink=1.0-smoothstep(0.85,1.0,sin(uT*2.1)*0.5+0.5)*0.95;
    // halo
    c=mix(c, c*0.25, smoothstep(1.3,0.6,length(q))*0.7);
    c=eye(c,q,look,blink,uSeed,uPrm.z);
  }
  return c;
}
// 2 grid of eyes (ref: eye patterns)
vec3 sEyes(vec2 p){
  float n=uPrm.x; // eyes per row ~2.5..6
  vec2 g=p*n*0.5;
  g.y+=uT*uPrm.y*0.4;
  float row=floor(g.y);
  g.x+=mod(row,2.0)*0.5 + sin(row*1.7+uT*0.7)*0.15*uPrm.z;
  vec2 id=floor(g), q=fract(g)-0.5;
  float ph=hash21(id);
  vec3 bg=mix(stop(uPal,0)*0.85, stop(uPal,0)*0.45, fbm(p*4.0+uT*0.2));
  bg=mix(bg, stop(uPal,3), smoothstep(0.45,0.5,length(q))*0.3);
  // blink: per-eye phase locked to beat
  float bp=fract(uBeat*0.5+ph);
  float open=smoothstep(0.0,0.12,bp)*smoothstep(1.0,0.82,bp);
  open=mix(1.0, open, step(0.55,ph)); // ~half the eyes blink
  vec2 target=vec2(sin(uT*0.8)*0.8, cos(uT*0.6)*1.2);
  vec2 dir=normalize(target-(id+0.5)/(n*0.5)+1e-4);
  vec3 c=eye(bg, q*vec2(2.2,2.2)*(1.0-0.06*uKick), dir*0.22, open, ph*10.0, step(0.8,ph));
  return c;
}
// 3 liquid acid marble
vec3 sLiquid(vec2 p){
  p*=uPrm.x; // scale ~1..2
  float t=uT*0.25*uPrm.y;
  vec2 q=vec2(fbm(p+t), fbm(p+vec2(5.2,1.3)-t));
  vec2 r=vec2(fbm(p+3.5*q+vec2(1.7,9.2)+t*1.3), fbm(p+3.5*q+vec2(8.3,2.8)-t));
  float f=fbm(p+3.0*r+uBass*0.3);
  float bands=uPrm.z; // contour sharpness
  float x=f*2.0+length(q)*0.8+uT*0.08;
  vec3 c=pal(x);
  float ct=fract(x*bands);
  c=mix(c, c*0.25, smoothstep(0.08,0.0,min(ct,1.0-ct))*uPrm.w);
  return c*(0.85+0.3*uRms);
}
// 4 checker tunnel / infinite floor
vec3 sTunnel(vec2 p){
  vec3 c;
  if(uPrm.w<0.5){
    float r=length(p), a=atan(p.y,p.x);
    a+=uT*0.3+0.6/(r+0.2)*sin(uT*0.7)*uPrm.z;
    vec2 uv=vec2(a/PI*uPrm.x, 1.6/(r+1e-3)+uT*uPrm.y*2.0);
    float ch=mod(floor(uv.x)+floor(uv.y),2.0);
    vec3 col=palHard(floor(uv.y)*0.25);
    c=mix(vec3(0.02), col, ch);
    c=mix(c, vec3(0.96), ch*step(0.5,fract(floor(uv.y)*0.5))*0.6);
    c*=smoothstep(0.0,0.5,r); // depth fog
  } else {
    // floor + ceiling checkerboard with horizon
    float y=p.y+0.2*sin(uT*0.6);
    float z=0.5/(abs(y)+1e-3);
    vec2 uv=vec2(p.x*z*uPrm.x + sin(uT*0.4)*2.0, z+uT*uPrm.y*2.0);
    float ch=mod(floor(uv.x)+floor(uv.y),2.0);
    vec3 col=mix(stop(uPal,0),stop(uPal,1),ch);
    col=mix(col,palHard(floor(uv.y)*0.25+0.5), step(0.0,y)*0.7);
    c=mix(col, stop(uPal,2), smoothstep(6.0,40.0,z)); // horizon glow
  }
  return c;
}
// 5 kaleidoscope fractal mandala
vec3 sKaleido(vec2 p){
  float seg=floor(uPrm.x+0.5);
  float r=length(p), a=atan(p.y,p.x)+uT*0.15;
  float sa=TAU/seg;
  a=mod(a,sa); a=abs(a-sa*0.5);
  vec2 q=vec2(cos(a),sin(a))*r;
  q*=1.0+0.15*uKick;
  float m=1e9; float tr=0.0;
  for(int i=0;i<7;i++){
    q=abs(q)/dot(q,q)-vec2(uPrm.y,uPrm.z)+0.07*vec2(sin(uT*0.4),cos(uT*0.3));
    float d=abs(length(q)-0.6);
    if(d<m){ m=d; tr=float(i); }
  }
  vec3 c=palHard(tr*0.25+uT*0.1);
  c=mix(c, pal(tr*0.31+0.5), smoothstep(0.25,0.0,m));
  c=mix(vec3(0.02), c, smoothstep(0.02,0.06,m)+step(0.18,m)*0.0+smoothstep(0.0,0.02,abs(m-0.12)));
  return c;
}
// 6 julia recursion
vec3 sJulia(vec2 p){
  vec2 z=p*uPrm.x;
  float ang=uT*0.25*uPrm.y+uSeed;
  vec2 c=0.7885*vec2(cos(ang),sin(ang));
  float m=0.0; float it=0.0;
  for(int i=0;i<64;i++){
    z=vec2(z.x*z.x-z.y*z.y, 2.0*z.x*z.y)+c;
    m=dot(z,z);
    if(m>256.0) break;
    it+=1.0;
  }
  float sm=it-log2(log2(max(m,1.0001)))+4.0;
  vec3 col=palHard(sm*0.08+uT*0.15);
  col=mix(col, pal(sm*0.08+0.37), 0.35);
  float bands=fract(sm*0.5);
  col=mix(col,vec3(0.02),smoothstep(0.12,0.0,min(bands,1.0-bands))*uPrm.z);
  col=mix(col, vec3(0.01), step(63.0,it));
  return col;
}
// 7 warped concentric rings + moon (ref: desert op-art)
vec3 sRings(vec2 p){
  vec2 c0=vec2(0.0,0.45);
  float d=length(p-c0);
  d+=0.06*sin(p.x*5.0+uT*1.3)+0.05*sin(p.y*4.0-uT*0.9)*uPrm.y;
  float f=fract(d*uPrm.x-uT*0.7);
  vec3 c=mix(stop(uPal,0),stop(uPal,2),step(0.5,f));
  c=mix(c,stop(uPal,1),smoothstep(0.6,1.4,d)*step(0.5,f)*0.8);
  // moon
  float mr=0.32+0.04*uBass;
  float md=length(p-c0);
  vec3 moon=stop(uPal,3)*(0.55+0.5*fbm((p-c0)*6.0))+0.15;
  moon*=0.6+0.5*clamp(dot(normalize(vec3(p-c0,sqrt(max(mr*mr-md*md,0.0)))),normalize(vec3(-0.4,0.5,0.8))),0.0,1.0);
  c=mix(c,moon,smoothstep(mr,mr-0.01,md));
  c+=stop(uPal,3)*smoothstep(mr+0.25,mr,md)*0.25*(0.5+uBass);
  return c;
}
// 8 melting acid smiley with spiral eyes
vec3 sSmiley(vec2 p){
  // background: rotating rays
  float a=atan(p.y,p.x), r=length(p);
  vec3 c=mix(stop(uPal,0),stop(uPal,3),step(0.5,fract(a/TAU*16.0+uT*0.2+0.1*sin(r*5.0-uT*3.0))));
  vec2 q=p/uPrm.x; // face scale
  q.y-=0.05*sin(uT*3.0);
  q*=1.0-0.08*uKick;
  // melt: drips below the face
  float melt=uPrm.y;
  float drip=melt*(0.25+0.35*noise(vec2(q.x*7.0,1.0)))*smoothstep(0.2,-0.6,q.y);
  vec2 mq=vec2(q.x, q.y+drip*(0.5+0.5*sin(uT*0.8)));
  float fd=length(mq)-0.62;
  vec3 yellow=vec3(1.0,0.86,0.05);
  vec3 face=yellow*(0.8+0.25*smoothstep(0.6,-0.2,mq.y));
  // spiral eyes
  for(int k=0;k<2;k++){
    vec2 e=q-vec2(k==0?-0.22:0.22,0.16);
    float er=length(e), ea=atan(e.y,e.x);
    float sp=fract(ea/TAU+log(er+0.01)*1.4-uT*(k==0?1.5:-1.5));
    vec3 ec=mix(vec3(0.02),vec3(1.0),step(0.5,sp));
    face=mix(face,ec,smoothstep(0.13,0.12,er));
  }
  // mouth arc (opens with bass)
  float mo=0.05+0.12*uBass*uPrm.z;
  vec2 m=q-vec2(0.0,-0.12);
  float md=abs(length(m*vec2(1.0,1.0+mo*4.0))-0.36)-0.03-mo*0.2;
  md=max(md,m.y+0.02);
  face=mix(face,vec3(0.02),smoothstep(0.012,0.0,md));
  c=mix(c,face,smoothstep(0.01,0.0,fd));
  c=mix(c,vec3(0.02),smoothstep(0.02,0.0,abs(fd))*0.95);
  return c;
}
// 9 hyperspace starfield with y2k sparkles
vec3 sWarp(vec2 p){
  vec3 c=mix(vec3(0.02,0.0,0.12), stop(uPal,3)*0.25, smoothstep(1.8,0.0,length(p)));
  float a=atan(p.y,p.x), r=length(p);
  for(int L=0;L<3;L++){
    float fl=float(L);
    float speed=uPrm.x*(1.0+fl*0.6);
    float cells=40.0+fl*25.0;
    float ac=floor(a/TAU*cells);
    float h=hash21(vec2(ac,fl));
    float z=fract(h*7.0 - uT*speed*0.25);
    float sr=z*z*2.2;
    float len=0.02+z*0.25*uPrm.y*(1.0+uKick);
    float da=abs(fract(a/TAU*cells)-0.5);
    float on=step(r,sr)*step(sr-len,r)*smoothstep(0.12,0.0,da);
    c+=pal(h+uT*0.1)*on*z*1.6;
  }
  // 4-point sparkles
  vec2 g=p*2.5; vec2 id=floor(g); vec2 q=fract(g)-0.5;
  float h=hash21(id+13.0);
  if(h>0.6){
    float tw=0.5+0.5*sin(uT*4.0+h*30.0);
    float s=max(0.0,0.03/(abs(q.x)*abs(q.y)*40.0+0.02)-0.05)*tw;
    s*=smoothstep(0.5,0.0,length(q));
    c+=vec3(1.0)*s*0.4;
  }
  return c;
}
// 10 moire interference
vec3 sMoire(vec2 p){
  vec2 c1=vec2(0.35*sin(uT*0.7),0.5*cos(uT*0.5));
  vec2 c2=-c1+vec2(0.0,0.1*sin(uT*1.3));
  float f=uPrm.x;
  float a=step(0.5,fract(length(p-c1)*f-uT*0.5));
  float b=step(0.5,fract(length(p-c2)*f+uT*0.3));
  float m=abs(a-b);
  vec3 col=mix(stop(uPal,0),stop(uPal,1),m);
  if(uPrm.y>0.5){ // tint by interference rings
    col=mix(col, pal(length(p)*0.5+uT*0.1), (1.0-m)*0.5);
  }
  return col;
}
// 11 truchet op-art
vec3 sTruchet(vec2 p){
  p+=vec2(0.0,uT*0.15*uPrm.y);
  p+=0.05*vec2(sin(p.y*4.0+uT),cos(p.x*4.0-uT))*uPrm.z;
  vec2 g=p*uPrm.x, id=floor(g), q=fract(g)-0.5;
  float flip=step(0.5,hash21(id+floor(uBeat*0.25)));
  if(flip>0.5) q.x=-q.x;
  float d1=abs(length(q-vec2(0.5,0.5))-0.5);
  float d2=abs(length(q+vec2(0.5,0.5))-0.5);
  float d=min(d1,d2);
  float w=0.13+0.05*uKick;
  float line=smoothstep(w+0.02,w,d);
  float stripes=step(0.5,fract(d*9.0-uT*1.5));
  vec3 c=mix(stop(uPal,1), mix(stop(uPal,0),stop(uPal,2),stripes), line);
  return c;
}
// 12 droste recursion — infinite zoom through nested frames
vec3 sDroste(vec2 p){
  float r=length(p), a=atan(p.y,p.x);
  float k=uPrm.x;                    // twist
  float scale=log(uPrm.y);           // zoom factor per level (e.g. 2.2)
  float w=log(r+1e-5) - uT*0.45*uPrm.z;
  float lvl=floor(w/scale);
  float fw=fract(w/scale);
  float ang=a + w*k;
  // square frame in each level
  vec2 q=vec2(cos(ang),sin(ang))*exp(fw*scale);
  float sq=max(abs(q.x),abs(q.y));
  float frame=step(0.5,fract(sq*2.0));
  vec3 c=mix(palHard(lvl*0.25), palHard(lvl*0.25+0.5), frame);
  // eye at the deepest point of every level
  float ed=length(q);
  c=mix(c, vec3(0.02), smoothstep(0.55,0.53,ed)*0.0);
  float stripe=fract(ang/TAU*8.0);
  c=mix(c, c*0.35, smoothstep(0.03,0.0,min(stripe,1.0-stripe))*0.6);
  return c;
}
// 13 melting rainbow drips
vec3 sMelt(vec2 p){
  float x=p.x*uPrm.x;
  // drip profile: smooth noise across x, long fingers that sag over time
  float dn=noise(vec2(x,3.1))*0.6+noise(vec2(x*2.7,7.7))*0.4;
  float drip=pow(dn,3.0)*uPrm.y*(1.2+0.6*sin(uT*0.7+x));
  float y=p.y+drip+uT*0.35*uPrm.z;
  float band=y*2.2;
  vec3 c=palHard(floor(band)*0.25);
  float e=fract(band);
  c=mix(c, c*0.35, smoothstep(0.06,0.0,min(e,1.0-e)));      // dark seams
  c+=vec3(0.25)*smoothstep(0.08,0.0,abs(e-0.15))*0.6;        // glossy highlight
  return c;
}
// 14 giant hypno eye with op-art rays
vec3 sBigEye(vec2 p){
  float r=length(p), a=atan(p.y,p.x);
  vec3 c=mix(stop(uPal,0),stop(uPal,1),step(0.5,fract(a/TAU*28.0+r*0.6*sin(uT*0.5)-uT*0.1)));
  c=mix(c, vec3(0.02), smoothstep(0.03,0.0,abs(fract(r*2.0-uT*0.8)-0.5)-0.46)*0.5);
  float s=uPrm.x;
  vec2 q=p/s;
  vec2 look=vec2(0.12*sin(uT*1.1), 0.05*cos(uT*1.7));
  float blinkPhase=fract(uT*uPrm.y);
  float open=1.0-0.97*smoothstep(0.9,0.95,blinkPhase)*smoothstep(1.0,0.95,blinkPhase);
  open*=1.0+0.08*uKick;
  // lashes
  float lid=sdAlmond(q,0.98,0.42*open);
  float la=atan(q.y,q.x);
  float lash=step(0.0,q.y)*smoothstep(0.02,0.0,abs(fract(q.x*9.0)-0.5)-0.42)*smoothstep(0.18,0.0,lid)*step(0.0,lid);
  c=mix(c,vec3(0.02),lash);
  c=eye(c,q,look,open,uSeed*3.0,1.0);
  return c;
}

vec3 scene(int id, vec2 p){
  if(id==0) return sSpiral(p);
  if(id==1) return sOpRadial(p);
  if(id==2) return sEyes(p);
  if(id==3) return sLiquid(p);
  if(id==4) return sTunnel(p);
  if(id==5) return sKaleido(p);
  if(id==6) return sJulia(p);
  if(id==7) return sRings(p);
  if(id==8) return sSmiley(p);
  if(id==9) return sWarp(p);
  if(id==10) return sMoire(p);
  if(id==11) return sTruchet(p);
  if(id==12) return sDroste(p);
  if(id==13) return sMelt(p);
  return sBigEye(p);
}

void main(){
  vec2 p=(gl_FragCoord.xy-0.5*uRes)/(0.5*uRes.x);
  p=rot(uRot)*p/uZoom;
  vec3 c=scene(SCENE,p);
  fragColor=vec4(clamp(c,0.0,1.0),1.0);
}
