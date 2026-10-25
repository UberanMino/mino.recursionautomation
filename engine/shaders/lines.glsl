// mino.recursion "line" library — minimal line-art / op-art, one accent colour per clip.
// Same uniform interface as scenes.glsl. uPal = accent index, uPrm.w = background (0 black, 1 off-white).
precision highp float;
precision highp int;

uniform vec2 uRes;
uniform float uT;
uniform int uPal;
uniform vec4 uPrm;
uniform float uSeed;
uniform float uZoom;
uniform float uRot;
uniform float uBass, uKick, uOnset, uHigh, uRms;
uniform float uBeat;
uniform float uEnergy;

out vec4 fragColor;

#define PI 3.14159265
#define TAU 6.28318531

mat2 rot(float a){ float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }
float hash21(vec2 p){ p=fract(p*vec2(123.34,456.21)+uSeed*0.137); p+=dot(p,p+45.32); return fract(p.x*p.y); }
float hash11(float n){ return fract(sin(n*127.1+uSeed*13.7)*43758.5453); }
float noise(vec2 p){
  vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(hash21(i),hash21(i+vec2(1,0)),u.x), mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),u.x), u.y);
}
// anti-aliased line mask for a distance field value d (0 on the line), half width w
float L(float d, float w){ float aa=fwidth(d)*1.2+1e-5; return smoothstep(w+aa, w-aa, abs(d)); }
// line of roughly constant pixel width px, for fields whose scale changes a lot across the frame
float LP(float d, float px){ return 1.0-smoothstep(px*0.5, px*0.5+1.2, abs(d)/max(fwidth(d),1e-5)); }
float segD(vec2 p, vec2 a, vec2 b){ vec2 pa=p-a, ba=b-a; float h=clamp(dot(pa,ba)/dot(ba,ba),0.0,1.0); return length(pa-ba*h); }

vec3 accent(){
  if(uPal==0) return vec3(0.16,1.00,0.55);   // mint green
  if(uPal==1) return vec3(0.42,0.24,1.00);   // violet
  if(uPal==2) return vec3(1.00,0.23,0.83);   // magenta
  if(uPal==3) return vec3(0.16,0.28,1.00);   // cobalt
  if(uPal==4) return vec3(1.00,0.48,0.19);   // orange
  if(uPal==5) return vec3(1.00,0.16,0.24);   // red
  if(uPal==6) return vec3(0.10,0.42,0.22);   // deep green (ink on white)
  return vec3(0.85,0.85,0.90);               // silver
}
bool WHITE(){ return uPrm.w>0.5; }
vec3 BG(){ return WHITE() ? vec3(0.95,0.94,0.96) : vec3(0.0); }
vec3 INK(){ return WHITE() ? vec3(0.03,0.03,0.05) : vec3(0.97); }
// draw mask m in accent; on black it glows, on white it is ink-like
vec3 paint(vec3 c, float m, vec3 col){ return mix(c, col, clamp(m,0.0,1.0)); }
vec3 ac(){ return WHITE() ? accent()*0.75 : accent(); }

// 0 basket weave, wave-distorted
vec3 lWeave(vec2 p){
  float n=uPrm.x;                                   // cells across ~4..7
  vec2 q=p*n*0.5;
  q.y+=0.45*sin(q.x*0.9+uT*1.4)+0.25*sin(q.x*2.1-uT*0.8);
  q.x+=0.25*sin(q.y*0.7+uT);
  vec2 c=floor(q), f=fract(q);
  bool hor=mod(c.x+c.y,2.0)<1.0;
  float s=hor?f.y:f.x;
  float strands=2.0;
  float k=fract(s*strands);
  float gap=smoothstep(0.0,0.12,k)*smoothstep(1.0,0.88,k);
  float e=hor?f.x:f.y;                              // shade towards cell ends (over/under)
  vec3 strand=mix(INK()*0.0+BG(), BG()*0.85, smoothstep(0.35,0.5,abs(e-0.5)));
  vec3 col=mix(WHITE()?vec3(0.02):vec3(0.0), WHITE()?BG():vec3(0.92), gap);
  col=mix(col, col*0.55, smoothstep(0.30,0.5,abs(e-0.5))*gap);
  col=paint(col, L(k-0.5,0.5-0.12)*0.0 + (1.0-smoothstep(0.0,0.03,k))*gap*0.0, ac());
  float edge=L(min(k,1.0-k),0.012);
  return paint(col, edge*0.9, ac());
}
// 1 wireframe tunnel (polar grid)
vec3 lTunnel(vec2 p){
  float r=length(p), a=atan(p.y,p.x)+uT*0.15*uPrm.z;
  float z=0.6/(r+0.02);
  float rings=fract(z*uPrm.x*0.25 - uT*uPrm.y);
  float spokes=fract(a/TAU*floor(uPrm.x*3.0));
  float m=max(L(rings-0.5,0.5-0.03*r*2.0), 0.0);
  float lr=L(min(rings,1.0-rings), 0.02+0.02*r);
  float ls=L(min(spokes,1.0-spokes), 0.006+0.012*r);
  float fade=smoothstep(0.02,0.6,r);
  vec3 c=BG();
  c=paint(c, max(lr,ls)*fade, ac());
  return c;
}
// 2 neon wire room with a floating cube
vec3 cubeLines(vec2 p, float s, float t){
  float d=1e9;
  vec3 v[8];
  for(int i=0;i<8;i++){
    vec3 q=vec3(float(i&1)*2.0-1.0, float((i>>1)&1)*2.0-1.0, float((i>>2)&1)*2.0-1.0);
    q.xz=rot(t*0.7)*q.xz; q.yz=rot(t*0.45)*q.yz;
    v[i]=q;
  }
  for(int i=0;i<8;i++){
    for(int b=0;b<3;b++){
      int j=i^(1<<b);
      if(j>i){
        vec2 a2=v[i].xy*s/(2.6-v[i].z*0.5), b2=v[j].xy*s/(2.6-v[j].z*0.5);
        d=min(d, segD(p,a2,b2));
      }
    }
  }
  return vec3(d,0,0);
}
vec3 lRoom(vec2 p){
  float m=max(abs(p.x),abs(p.y)*0.62);
  float z=0.35/(m+1e-3);
  float u=abs(p.x)>abs(p.y)*0.62 ? p.y/abs(p.x) : p.x/(abs(p.y)*0.62);
  float gz=fract(z*1.2-uT*uPrm.y*0.6);
  float gu=fract(u*uPrm.x*0.5+0.5);
  vec3 c=BG();
  float glow=exp(-m*2.5)*0.0+smoothstep(0.0,1.0,m)*0.55;
  c=mix(c, ac()*0.35, glow*(WHITE()?0.3:1.0));
  float lines=max(L(min(gz,1.0-gz),0.03), L(min(gu,1.0-gu),0.02));
  c=paint(c, lines*smoothstep(0.03,0.3,m), WHITE()?ac():mix(ac(),vec3(1),0.55));
  float d=cubeLines(p, 0.45+0.05*uKick, uT).x;
  c=paint(c, L(d,0.004), WHITE()?INK():mix(ac(),vec3(1),0.4));
  return c;
}
// 3 rotating tesseract wireframe
vec3 lTesseract(vec2 p){
  vec4 v[16];
  float t=uT*0.6;
  for(int i=0;i<16;i++){
    vec4 q=vec4(float(i&1)*2.0-1.0, float((i>>1)&1)*2.0-1.0, float((i>>2)&1)*2.0-1.0, float((i>>3)&1)*2.0-1.0);
    q.xw=rot(t)*q.xw; q.yz=rot(t*0.7)*q.yz; q.zw=rot(t*0.4)*q.zw;
    v[i]=q;
  }
  float d=1e9;
  vec2 pr[16];
  for(int i=0;i<16;i++){ vec3 a=v[i].xyz/(2.4-v[i].w*0.6); pr[i]=a.xy/(3.0-a.z)*uPrm.x*2.2; }
  for(int i=0;i<16;i++){ for(int b=0;b<4;b++){ int j=i^(1<<b); if(j>i) d=min(d, segD(p,pr[i],pr[j])); } }
  vec3 c=BG();
  if(!WHITE()) c+=ac()*0.6*exp(-d*30.0);
  c=paint(c, L(d,0.005), WHITE()?ac():mix(ac(),vec3(1),0.35));
  float dots=1e9; for(int i=0;i<16;i++) dots=min(dots,length(p-pr[i]));
  c=paint(c, L(dots,0.012), WHITE()?INK():vec3(1));
  return c;
}
// 4 striped sphere over wavy lines
vec3 lStripeSphere(vec2 p){
  float R=uPrm.x;
  float n=uPrm.y*10.0;
  float y=p.y+0.06*sin(p.x*3.0+uT*1.5)*smoothstep(R*0.8,R*1.6,length(p));
  float bgL=fract(y*n*0.5);
  vec3 c=BG();
  c=paint(c, L(min(bgL,1.0-bgL),0.08), ac());
  float r=length(p);
  if(r<R){
    float sx=sqrt(max(R*R-p.x*p.x,1e-4));
    float yy=asin(clamp(p.y/sx,-1.0,1.0));
    float s=fract(yy/PI*n*0.6+uT*0.5);
    c=BG();
    c=paint(c, L(min(s,1.0-s),0.12), ac());
    c=mix(c, c*0.6, smoothstep(R*0.7,R,r)*0.5);
  }
  c=paint(c, L(r-R,0.006), WHITE()?ac()*0.6:ac());
  return c;
}
// 5 sphere of dashes (particles)
vec3 lDashSphere(vec2 p){
  float R=uPrm.x*(1.0+0.04*uKick);
  float r=length(p);
  vec3 c=BG();
  if(r<R){
    vec3 n=vec3(p/R, sqrt(1.0-r*r/(R*R)));
    n.xz=rot(uT*0.5)*n.xz; n.yz=rot(0.4)*n.yz;
    float lat=asin(n.y), lon=atan(n.z,n.x);
    vec2 g=vec2(lon/TAU*uPrm.y*30.0, lat/PI*uPrm.y*15.0);
    vec2 id=floor(g), f=fract(g)-0.5;
    float h=hash21(id);
    float on=step(0.15,h);
    float dash=L(f.y,0.06)*smoothstep(0.42,0.3,abs(f.x+(h-0.5)*0.2));
    float swirl=0.5+0.5*sin(lat*6.0+lon*2.0+uT);
    c=paint(c, dash*on*(0.6+0.4*swirl), ac());
  }
  return c;
}
// 6 checkerboard wormhole (hourglass)
vec3 lWormhole(vec2 p){
  float y=p.y;
  float s=0.18+pow(abs(y)*0.6,1.6);
  float x=p.x/s;
  float v=sign(y)*log(abs(y)+0.05)*2.0 - uT*uPrm.y*sign(y);
  float ch=mod(floor(x*uPrm.x*0.5+0.5*sin(uT*0.4))+floor(v*uPrm.x*0.25),2.0);
  vec3 c=mix(vec3(0.02), vec3(0.95), ch);
  float throat=smoothstep(0.8,0.0,abs(y));
  c=mix(c, mix(c, ac(), 0.75*ch+0.25), throat*0.6);
  c*=smoothstep(4.0,1.5,abs(x));
  return c;
}
// 7 isometric cube lattice
vec3 lIsoCubes(vec2 p){
  p.y+=uT*0.12*uPrm.y;
  vec2 q=p*uPrm.x;
  // hex grid
  const vec2 s=vec2(1.0,1.7320508);
  vec4 hc=floor(vec4(q,q-vec2(0.5,1.0))/s.xyxy)+0.5;
  vec4 h=vec4(q-hc.xy*s, q-(hc.zw+0.5)*s);
  vec2 g=dot(h.xy,h.xy)<dot(h.zw,h.zw)?h.xy:h.zw;
  // hexagon edge distance
  vec2 a=abs(g);
  float hex=max(dot(a,s*0.5),a.x);
  float d=abs(hex-0.5);
  // three inner edges from the centre to alternate vertices -> isometric cube
  float inner=min(segD(g,vec2(0),vec2(0.0,-0.577)), min(segD(g,vec2(0),vec2(0.5,0.2887)), segD(g,vec2(0),vec2(-0.5,0.2887))));
  float m=max(L(d,0.018), L(inner,0.012)*step(hex,0.5));
  vec3 c=BG();
  float shade=(g.y>0.2887*abs(g.x)/0.5) ? 2.0 : (g.x>0.0?1.0:0.0);
  if(!WHITE()) c+=ac()*0.06*shade*step(hex,0.5);
  return paint(c, m, ac());
}
// 8 radial fibre burst
vec3 lBurst(vec2 p){
  float r=length(p), a=atan(p.y,p.x)+uT*0.08;
  float bins=900.0;
  float id=floor((a/TAU+0.5)*bins);
  float h=hash11(id), h2=hash11(id+31.0);
  float r0=uPrm.x*(0.85+0.3*h2)*(1.0-0.08*uKick);
  float len=0.25+0.9*h*(0.7+0.5*uBass);
  float fa=fract((a/TAU+0.5)*bins)-0.5;
  float on=step(r0,r)*step(r,r0+len);
  float line=smoothstep(0.5,0.1,abs(fa))*on*smoothstep(r0+len,r0+len*0.6,r);
  vec3 c=BG();
  vec3 col=mix(ac(), WHITE()?INK():vec3(1), step(0.93,h2));
  c=paint(c, line*(0.5+0.5*h), col);
  float tip=smoothstep(0.012,0.0,abs(r-(r0+len)))*on*step(0.8,h);
  c=paint(c, tip, WHITE()?INK():vec3(1));
  return c;
}
// 9 receding squares / dots tunnel
vec3 lDots(vec2 p){
  float r=uPrm.z>0.5 ? max(abs(p.x),abs(p.y)) : length(p);
  float a=atan(p.y,p.x);
  float w=log(r+1e-4)*uPrm.x - uT*uPrm.y;
  float ring=floor(w);
  float fr=fract(w)-0.5;
  float cnt=floor(10.0+4.0*mod(ring,3.0));
  float fa=fract(a/TAU*cnt + ring*0.5)-0.5;
  vec2 cell=vec2(fa*TAU/cnt*uPrm.x*1.15, fr);
  float sz=0.28;
  float d = uPrm.z>0.5 ? max(abs(cell.x),abs(cell.y))-sz : length(cell)-sz;
  vec3 c=BG();
  float shade=0.55+0.45*mod(ring,2.0);
  vec3 col=mix(ac()*shade, WHITE()?INK():vec3(1), step(1.5,mod(ring,4.0))*0.6);
  c=paint(c, smoothstep(0.03,-0.03,d)*smoothstep(0.0,0.08,r), col);
  return c;
}
// 10 zigzag swirl (black / white)
vec3 lZigzag(vec2 p){
  float r=length(p), a=atan(p.y,p.x);
  float arms=floor(uPrm.x);
  float tw=a + log(r+1e-3)*uPrm.y - uT*1.2;
  float z=fract(tw/TAU*arms + 0.18*(abs(fract(log(r+1e-3)*3.0-uT*0.5)-0.5)*2.0));
  float m=step(0.5,z);
  vec3 c=mix(vec3(0.02), vec3(0.96), m);
  float edge=L(min(z,1.0-z),0.02)+L(z-0.5,0.02);
  return paint(c, edge*0.8, ac());
}
// 11 laser tunnel
vec3 lLasers(vec2 p){
  vec3 c=BG();
  for(int i=0;i<9;i++){
    float fi=float(i);
    float an=fi*0.71+uT*(0.25+0.05*fi)*(mod(fi,2.0)*2.0-1.0);
    vec2 dir=vec2(cos(an),sin(an));
    float off=0.15+0.12*fi*uPrm.x+0.1*sin(uT+fi);
    float d=abs(dot(p,vec2(-dir.y,dir.x))-off);
    float along=dot(p,dir);
    float w=0.004+0.012*hash11(fi);
    float m=L(d,w)*smoothstep(-1.6,0.2,along);
    vec3 col=mix(ac(), mix(ac(),vec3(1),0.5), hash11(fi+3.0));
    if(!WHITE()) c+=col*exp(-d*60.0)*0.25;
    c=paint(c, m, col);
  }
  return c;
}
// 12 unknown-pleasures ridge lines
vec3 lRidges(vec2 p){
  vec3 c=BG();
  float n=uPrm.x;          // number of lines
  float top=0.9, bot=-0.9;
  for(int i=0;i<48;i++){
    float fi=float(i);
    if(fi>=n) break;
    float y0=top-(top-bot)*fi/(n-1.0);
    float cx=exp(-pow(p.x*2.2,2.0));
    float h=(noise(vec2(p.x*7.0+fi*3.1, uT*1.2+fi))*0.8+noise(vec2(p.x*15.0, fi+uT*2.0))*0.3)*cx*uPrm.y*(0.6+0.6*uBass);
    float y=y0+h*0.35;
    if(p.y<y) c=BG();                         // occlude what's behind
    c=paint(c, L(p.y-y,0.004)*step(p.y,y+0.02), ac());
  }
  return c;
}


// ---------- silhouettes ----------
float sdCirc(vec2 p, vec2 c, float r){ return length(p-c)-r; }
float sdEll(vec2 p, vec2 c, vec2 r){ vec2 q=(p-c)/r; return (length(q)-1.0)*min(r.x,r.y); }
float sdBoxR(vec2 p, vec2 c, vec2 b, float rr){ vec2 d=abs(p-c)-b+rr; return length(max(d,0.0))+min(max(d.x,d.y),0.0)-rr; }
float sdCap(vec2 p, vec2 a, vec2 b, float r){ return segD(p,a,b)-r; }
float smin(float a, float b, float k){ float h=clamp(0.5+0.5*(b-a)/k,0.0,1.0); return mix(b,a,h)-k*h*(1.0-h); }
float sdTri(vec2 p, float r){ const float k=1.7320508; p.x=abs(p.x)-r; p.y=p.y+r/k; if(p.x+k*p.y>0.0) p=vec2(p.x-k*p.y,-k*p.x-p.y)/2.0; p.x-=clamp(p.x,-2.0*r,0.0); return -length(p)*sign(p.y); }
float sdStar5(vec2 p, float r, float rf){
  const vec2 k1=vec2(0.809016994375,-0.587785252292); const vec2 k2=vec2(-k1.x,k1.y);
  p.x=abs(p.x); p-=2.0*max(dot(k1,p),0.0)*k1; p-=2.0*max(dot(k2,p),0.0)*k2; p.x=abs(p.x); p.y-=r;
  vec2 ba=rf*vec2(-k1.y,k1.x)-vec2(0,1); float h=clamp(dot(p,ba)/dot(ba,ba),0.0,r); return length(p-ba*h)*sign(p.y*ba.x-p.x*ba.y);
}
float sdHeart(vec2 p){ p.x=abs(p.x); if(p.y+p.x>1.0) return sqrt(dot(p-vec2(0.25,0.75),p-vec2(0.25,0.75)))-sqrt(2.0)/4.0;
  return sqrt(min(dot(p-vec2(0.0,1.0),p-vec2(0.0,1.0)), dot(p-0.5*max(p.x+p.y,0.0),p-0.5*max(p.x+p.y,0.0))))*sign(p.x-p.y); }
float shapeSD(int id, vec2 p){
  if(id==0){ // bust, back of head
    float h=sdEll(p,vec2(0.0,0.38),vec2(0.34,0.43));
    float n=sdBoxR(p,vec2(0.0,-0.1),vec2(0.17,0.2),0.06);
    float sh=max(sdEll(p,vec2(0.0,-0.62),vec2(0.82,0.36)), p.y+0.62-0.0*p.x-1.0);
    return smin(smin(h,n,0.08),sh,0.12);
  }
  if(id==1){ // head profile facing right
    float c=sdCirc(p,vec2(-0.06,0.38),0.42);
    float f=sdEll(p,vec2(0.12,0.12),vec2(0.27,0.36));
    float nose=sdCap(p,vec2(0.30,0.30),vec2(0.43,0.14),0.035);
    float lip=sdCirc(p,vec2(0.33,0.0),0.05);
    float chin=sdCirc(p,vec2(0.26,-0.14),0.08);
    float neck=sdBoxR(p,vec2(-0.03,-0.26),vec2(0.17,0.17),0.05);
    float d=smin(c,f,0.1); d=smin(d,nose,0.06); d=smin(d,lip,0.04); d=smin(d,chin,0.06); d=smin(d,neck,0.08);
    return d;
  }
  if(id==2){ // figure, arms spread (floating)
    float d=sdCirc(p,vec2(0.0,0.78),0.14);
    d=smin(d,sdCap(p,vec2(0.0,0.58),vec2(0.0,-0.08),0.15),0.08);
    d=smin(d,sdCap(p,vec2(-0.08,0.48),vec2(-0.62,0.66),0.055),0.06);
    d=smin(d,sdCap(p,vec2(0.08,0.48),vec2(0.62,0.66),0.055),0.06);
    d=smin(d,sdCap(p,vec2(-0.07,-0.1),vec2(-0.16,-0.92),0.075),0.06);
    d=smin(d,sdCap(p,vec2(0.07,-0.1),vec2(0.16,-0.92),0.075),0.06);
    return d;
  }
  if(id==3){ // open hand
    float d=sdBoxR(p,vec2(0.0,-0.25),vec2(0.29,0.32),0.13);
    d=smin(d,sdCap(p,vec2(-0.21,0.0),vec2(-0.26,0.52),0.062),0.04);
    d=smin(d,sdCap(p,vec2(-0.07,0.05),vec2(-0.08,0.70),0.065),0.04);
    d=smin(d,sdCap(p,vec2(0.07,0.05),vec2(0.09,0.66),0.065),0.04);
    d=smin(d,sdCap(p,vec2(0.21,0.0),vec2(0.26,0.48),0.06),0.04);
    d=smin(d,sdCap(p,vec2(-0.27,-0.25),vec2(-0.58,0.05),0.07),0.05);
    d=smin(d,sdBoxR(p,vec2(0.0,-0.78),vec2(0.2,0.25),0.05),0.06);
    return d;
  }
  if(id==4){ // mushroom
    float cap=max(sdEll(p,vec2(0.0,0.22),vec2(0.62,0.42)), -(p.y-0.12));
    float stem=sdCap(p,vec2(0.0,0.14),vec2(0.0,-0.62),0.14);
    return smin(cap,stem,0.05);
  }
  if(id==5){ // cat head
    float d=sdEll(p,vec2(0.0,0.0),vec2(0.46,0.40));
    vec2 q=p-vec2(0.27,0.38); q=rot(-0.3)*q; d=smin(d,sdTri(q,0.17),0.04);
    q=p-vec2(-0.27,0.38); q=rot(0.3)*q; d=smin(d,sdTri(q,0.17),0.04);
    return d;
  }
  if(id==6){ // eye
    float R=(0.9*0.9+0.38*0.38)/(2.0*0.38);
    return max(length(p-vec2(0.0,0.38-R))-R, length(p+vec2(0.0,0.38-R))-R);
  }
  if(id==7) return sdTri(p+vec2(0.0,0.1),0.62);                 // pyramid
  if(id==8){ // planet with ring
    float pl=sdCirc(p,vec2(0.0),0.36);
    vec2 q=rot(0.35)*p; float ring=abs(sdEll(q,vec2(0.0),vec2(0.72,0.17)))-0.025;
    ring=max(ring, -(pl-0.02)*step(0.0,q.y));
    return min(pl,ring);
  }
  if(id==9) return sdHeart(p*1.25+vec2(0.0,0.62))/1.25;
  if(id==11){ // alien head with almond eyes cut out
    float d=smin(sdEll(p,vec2(0.0,0.18),vec2(0.44,0.46)), sdEll(p,vec2(0.0,-0.28),vec2(0.17,0.32)),0.22);
    vec2 q=p-vec2(0.17,0.08); q=rot(-0.55)*q; float e=sdEll(q,vec2(0.0),vec2(0.15,0.07));
    q=p-vec2(-0.17,0.08); q=rot(0.55)*q; e=min(e,sdEll(q,vec2(0.0),vec2(0.15,0.07)));
    return max(d,-e);
  }
  if(id==12) return max(sdCirc(p,vec2(0.0),0.58), -sdCirc(p,vec2(0.26,0.14),0.5));   // crescent moon
  if(id==13){ // crystal: cut gem standing on its tip
    float hw=p.y>0.15 ? 0.42-(p.y-0.15)*0.6 : 0.42*(p.y+0.62)/0.77;
    return max(max(abs(p.x)-hw, p.y-0.45), -0.62-p.y)*0.8;
  }
  if(id==14) return min(sdCirc(p,vec2(0.0,0.22),0.3), sdBoxR(p,vec2(0.0,-0.3),vec2(0.17,0.42),0.02));   // keyhole
  return sdStar5(p,0.6,0.45);
}
// 13 silhouette: prm.x shape, prm.y fill style, prm.z scale
vec3 lSilhouette(vec2 p){
  int sh=int(uPrm.x);
  float sc=uPrm.z*(1.0+0.07*uKick);
  vec2 q=p/sc;
  q.y-=0.03*sin(uT*1.7);
  q=rot(0.08*sin(uT*0.9))*q;
  float d=shapeSD(sh,q)*sc;
  int fill=int(uPrm.y);
  vec3 c=BG();
  float edge=L(d,0.006);
  if(fill==0){                                   // topographic contour rings around and inside the shape
    float k=fract(d*14.0-uT*1.5);
    float rings=L(min(k,1.0-k),0.06)*smoothstep(0.9,0.0,abs(d));
    c=paint(c, rings*(d<0.0?0.55:1.0), ac());
    c=paint(c, edge, WHITE()?INK():vec3(1));
  } else if(fill==1){                            // solid silhouette with a glowing scribble inside
    vec3 sil=WHITE()?vec3(0.02):vec3(0.0);
    c=WHITE()?BG():mix(BG(),ac()*0.25,1.0);
    if(!WHITE()) c=mix(vec3(0.0),ac()*0.18,smoothstep(1.2,0.0,length(p)));
    if(d<0.0){
      c=sil;
      vec2 sp=p*6.0;
      float n1=noise(sp+vec2(uT*0.9,0.0)), n2=noise(sp*1.7-vec2(0.0,uT*1.1));
      float scr=L(fract(n1*4.0+n2*2.0)-0.5,0.03);
      float mask=smoothstep(0.0,-0.25,d)*smoothstep(0.55,0.05,length(q-vec2(0.0,0.4))+0.0*float(sh));
      c=paint(c, scr*(0.35+0.65*mask), mix(ac(),vec3(1),0.25));
    }
    c=paint(c, edge*0.6, ac());
  } else if(fill==2){                            // wireframe scanlines bulging over the form
    if(d<0.0){
      float bulge=sqrt(clamp(-d*3.0,0.0,1.0));
      float y=p.y*28.0+bulge*3.0*sin(p.x*3.0)-uT*2.0;
      float x=p.x*28.0/(0.4+bulge);
      float gl=max(L(fract(y)-0.5,0.08), L(fract(x)-0.5,0.05)*0.6);
      c=paint(c, gl*(0.4+0.6*bulge), ac());
    }
    c=paint(c, edge, WHITE()?INK():mix(ac(),vec3(1),0.5));
  } else if(fill==3){                            // neon outline with echo trails
    for(int i=0;i<5;i++){
      float fi=float(i);
      float s2=1.0+fi*0.16+0.08*fract(uT*0.8);
      float di=shapeSD(sh,q/s2)*sc*s2;
      c=paint(c, L(di,0.005)*(1.0-fi*0.18), ac());
      if(!WHITE()) c+=ac()*exp(-abs(di)*40.0)*0.15*(1.0-fi*0.2);
    }
    c=paint(c, edge, WHITE()?INK():vec3(1));
  } else {                                       // halftone dots inside, rings outside
    vec2 g=p*22.0; vec2 f=fract(g)-0.5;
    float r=0.42*smoothstep(0.0,-0.35,d);
    float dot_=smoothstep(r,r-0.08,length(f));
    c=paint(c, dot_*step(d,0.0), ac());
    float k=fract(d*6.0-uT); c=paint(c, L(min(k,1.0-k),0.05)*step(0.0,d)*smoothstep(0.8,0.0,d), ac()*0.6);
    c=paint(c, edge, WHITE()?INK():vec3(1));
  }
  return c;
}
// 14 field of floating wireframe cubes
vec3 lCubes(vec2 p){
  vec3 c=BG();
  float n=uPrm.x;                 // cubes per row (2..3)
  vec2 g=p*n*0.5; g.y+=uT*0.25*uPrm.y;
  vec2 id=floor(g), f=(fract(g)-0.5)*2.0/0.5*0.5;
  float h=hash21(id);
  float d=cubeLines(f, 1.25+0.15*uKick, uT*(0.6+h)+h*10.0).x;
  vec3 col=mix(ac(), WHITE()?INK():vec3(1), step(0.8,h));
  if(!WHITE()) c+=ac()*exp(-d*25.0)*0.25;
  c=paint(c, L(d,0.012), col);
  return c;
}

// ---------- library v2 (2026-10-21): more shots so reels stop looking alike ----------
// 15 see-through wireframe globe: back lines dim, front lines bright
float globeMask(vec2 p, float R, float side){
  float r=length(p);
  if(r>=R) return 0.0;
  vec3 n=vec3(p/R, side*sqrt(max(1.0-r*r/(R*R),0.0)));
  n.yz=rot(0.4)*n.yz;
  n.xz=rot(uT*uPrm.y)*n.xz;
  float nl=floor(uPrm.z);
  float gl=fract(asin(clamp(n.y,-1.0,1.0))/PI*nl+0.5), gm=fract(atan(n.z,n.x)/TAU*nl*1.5);
  return max(L(min(gl,1.0-gl),0.035), L(min(gm,1.0-gm),0.035));
}
vec3 lGlobe(vec2 p){
  float R=uPrm.x*(1.0+0.05*uKick);
  vec3 c=BG();
  if(!WHITE()) c+=ac()*0.10*smoothstep(R*1.6,R*0.6,length(p));
  c=paint(c, globeMask(p,R,-1.0)*0.35, ac());
  c=paint(c, globeMask(p,R,1.0), WHITE()?ac():mix(ac(),vec3(1),0.3));
  c=paint(c, L(length(p)-R,0.006), WHITE()?INK():vec3(1));
  vec2 q=rot(-0.3)*p; float k0=length(q/vec2(R*1.6,R*0.3)); float k1=length(q/(vec2(R*1.6,R*0.3)*vec2(R*1.6,R*0.3)));
  float ring=k0*(k0-1.0)/k1;
  c=paint(c, L(ring,0.005)*(1.0-step(length(p),R)*step(0.0,q.y)), ac());
  return c;
}
// 16 neon grid landscape: striped sun, hatched mountains, floor rushing towards the camera
vec3 lTerrain(vec2 p){
  float h=0.05;
  vec3 c=BG();
  vec2 sp=p-vec2(0.0,h+0.42);
  float sd=length(sp)-0.4;
  if(sd<0.0 && p.y>h){
    float yy=(p.y-h)/0.82;
    float band=fract(p.y*14.0-uT*0.7);
    c=paint(c, step(0.55*(1.0-yy),band), ac());
  }
  c=paint(c, L(sd,0.005)*step(h,p.y), ac());
  float mh=(noise(vec2(p.x*3.0,1.7))*0.65+noise(vec2(p.x*8.0,4.1))*0.25)*smoothstep(0.15,0.95,abs(p.x))*0.6*uPrm.z;
  float my=h+mh;
  if(p.y>h && p.y<my){
    c=BG();
    float k=fract((my-p.y)*38.0);
    c=paint(c, L(min(k,1.0-k),0.1)*0.55, ac());
  }
  c=paint(c, L(p.y-my,0.004)*step(h,p.y), WHITE()?INK():mix(ac(),vec3(1),0.5));
  if(p.y<h){
    float dz=h-p.y;
    float z=0.3/dz;
    float gz=fract(z-uT*uPrm.y);
    float gx=fract(p.x*z*uPrm.x*0.25+0.5);
    float m=max(LP(min(gz,1.0-gz),2.5), LP(min(gx,1.0-gx),2.0));
    c=paint(c, m*smoothstep(0.0,0.3,dz), ac());
    if(!WHITE()) c+=ac()*0.12*smoothstep(0.35,0.0,dz);
  }
  c=paint(c, L(p.y-h,0.004), WHITE()?INK():vec3(1));
  return c;
}
// 17 contour vortex: concentric lines bent into turning lobes
vec3 lVortex(vec2 p){
  float r=length(p), a=atan(p.y,p.x);
  float f=r*uPrm.y*10.0 + 0.7*sin(a*floor(uPrm.x)+log(r+0.02)*3.0*uPrm.z-uT*2.0)*smoothstep(0.0,0.6,r) - uT*1.5;
  float k=fract(f);
  float major=step(mod(floor(f+0.5),4.0),0.5);
  vec3 c=BG();
  c=paint(c, L(min(k,1.0-k),0.05+0.04*major)*smoothstep(0.02,0.15,r), major>0.5&&!WHITE()?mix(ac(),vec3(1),0.5):ac());
  return c;
}
// 18 harmonograph / lissajous figure with glow
vec3 lHarmono(vec2 p){
  float a=uPrm.x, b=uPrm.y;
  float ph=uT*0.35;
  float d=1e9;
  vec2 prev=vec2(0.0);
  for(int i=0;i<=120;i++){
    float u=float(i)/120.0*TAU;
    float e=0.86+0.14*cos(u*uPrm.z+uT*0.3);
    vec2 q=vec2(sin(a*u+ph)*0.82, sin(b*u+1.1)*1.25)*e;
    if(i>0) d=min(d, segD(p,prev,q));
    prev=q;
  }
  vec3 c=BG();
  if(!WHITE()) c+=ac()*exp(-d*28.0)*0.35;
  c=paint(c, L(d,0.004), WHITE()?ac():mix(ac(),vec3(1),0.45));
  return c;
}
// 19 recursive polygon tunnel: nested arches / triangles / squares / hexagons, each ring twisted
float sdNgon(vec2 p, float n, float r){
  if(n<2.5){
    float d=sdBoxR(p, vec2(0.0,-0.2*r), vec2(0.55*r,0.8*r), 0.0);
    return min(d, length(p-vec2(0.0,0.6*r))-0.55*r);
  }
  float seg=TAU/n;
  float an=mod(atan(p.x,p.y)+seg*0.5,seg)-seg*0.5;
  return length(p)*cos(an)-r*cos(seg*0.5);
}
vec3 lPolyTunnel(vec2 p){
  vec3 c=BG();
  float ph=fract(uT*uPrm.z);
  for(int i=0;i<18;i++){
    float fi=float(i)+ph;
    float s=0.025*pow(1.3,fi);
    if(s>3.5) break;
    vec2 q=rot(fi*uPrm.y)*p;
    float d=sdNgon(q,uPrm.x,s*(1.0+0.04*uKick));
    float w=0.0025+0.006*s;
    float fade=smoothstep(0.02,0.12,s);
    vec3 col=mod(float(i),3.0)<0.5 ? (WHITE()?INK():vec3(1)) : ac();
    c=paint(c, L(d,w)*fade, col);
    if(!WHITE()) c+=ac()*exp(-abs(d)*50.0)*0.06*fade;
  }
  return c;
}
// 20 plucked strings: vertical lines ringing in standing waves, hit by the kick
vec3 lStrings(vec2 p){
  vec3 c=BG();
  float n=floor(uPrm.x);
  for(int i=0;i<16;i++){
    float fi=float(i);
    if(fi>=n) break;
    float x0=(fi-(n-1.0)*0.5)/n*1.8;
    float k=floor(1.0+hash11(fi)*4.0);
    float amp=(0.025+0.10*uKick*hash11(fi+7.0)+0.03*uBass)*uPrm.y;
    float disp=amp*sin((p.y+1.8)/3.6*k*PI)*sin(uT*(5.0+fi*0.7)+fi*2.0);
    float d=p.x-x0-disp;
    vec3 col=WHITE()?ac():mix(ac(),vec3(1),0.5*hash11(fi+5.0));
    c=paint(c, L(d,0.003+0.003*hash11(fi+2.0)), col);
    if(!WHITE()) c+=ac()*exp(-abs(d)*70.0)*0.18;
  }
  return c;
}
// 21 double helix with rungs
vec3 lHelix(vec2 p){
  vec3 c=BG();
  float A=uPrm.x, k=uPrm.y*3.0;
  float ph=p.y*k+uT*1.6;
  float x1=A*sin(ph), z1=cos(ph);
  float slope=sqrt(1.0+pow(A*k*z1,2.0));
  float d1=abs(p.x-x1)/slope, d2=abs(p.x+x1)/slope;
  float dy=0.75/uPrm.z;
  float yc=(floor(p.y/dy)+0.5)*dy;
  float xr=A*sin(yc*k+uT*1.6);
  float dr=segD(p, vec2(-xr,yc), vec2(xr,yc));
  float zr=cos(yc*k+uT*1.6);
  vec3 dim=WHITE()?mix(BG(),ac(),0.45):ac()*0.4;
  c=paint(c, L(dr,0.003), dim);
  float dots=min(length(p-vec2(xr,yc)), length(p-vec2(-xr,yc)));
  c=paint(c, L(dots,0.014), WHITE()?INK():vec3(1));
  c=paint(c, L(z1<0.0?d1:d2,0.006), dim);
  c=paint(c, L(z1<0.0?d2:d1,0.008), WHITE()?ac():mix(ac(),vec3(1),0.3));
  if(!WHITE()) c+=ac()*exp(-min(d1,d2)*45.0)*0.2;
  return c;
}
// 22 line rain: falling dashes in columns, bright heads
vec3 lRain(vec2 p){
  vec3 c=BG();
  float cols=floor(uPrm.x);
  float x=p.x*cols*0.5;
  float id=floor(x), fx=fract(x)-0.5;
  float sp=0.6+1.4*hash11(id);
  float y=p.y*uPrm.y*2.0 + uT*sp*2.5 + hash11(id+3.0)*10.0;
  float yi=floor(y), fy=fract(y);
  float h=hash11(id*13.0+yi);
  float len=0.25+0.6*h;
  float on=step(fy,len)*step(0.3,h);
  float m=L(fx,0.08)*on;
  float head=smoothstep(len-0.08,len,fy)*on;
  if(!WHITE()) c+=ac()*exp(-abs(fx)*9.0)*0.25*on*fy/len;
  c=paint(c, m*(0.35+0.65*fy/len), ac());
  c=paint(c, L(fx,0.12)*head, WHITE()?INK():vec3(1));
  return c;
}
// 23 topographic map: moving contour lines of a warped noise field, every 5th line bold
vec3 lTopo(vec2 p){
  vec2 q=p*uPrm.x+vec2(uT*0.08,-uT*0.05);
  vec2 w=vec2(noise(q*0.7+uT*0.12), noise(q*0.7-uT*0.1+5.0));
  float f=noise(q+0.6*w)*0.65+noise(q*2.1+3.1)*0.25+noise(q*4.3+7.7)*0.1;
  float lev=f*uPrm.y*16.0-uT*0.6;
  float li=floor(lev+0.5);
  float d=lev-li;
  bool major=mod(li,5.0)<0.5;
  vec3 c=BG();
  c=paint(c, L(d, major?0.09:0.045), major?(WHITE()?INK():vec3(1)):ac());
  return c;
}
// 24 atom: tilted orbit ellipses, electrons running along them, pulsing nucleus
vec3 lOrbits(vec2 p){
  vec3 c=BG();
  float n=floor(uPrm.x), R=uPrm.y;
  vec2 e=vec2(R, R*0.3);
  for(int i=0;i<6;i++){
    float fi=float(i);
    if(fi>=n) break;
    vec2 q=rot(fi*PI/n+uT*0.12)*p;
    float k0=length(q/e), k1=length(q/(e*e));
    float d=k0*(k0-1.0)/k1;
    c=paint(c, L(d,0.004), ac());
    float th=uT*(1.6+fi*0.35)+fi*2.0;
    float de=length(q-e*vec2(cos(th),sin(th)));
    if(!WHITE()) c+=ac()*exp(-de*30.0)*0.5;
    c=paint(c, smoothstep(0.03,0.02,de), WHITE()?INK():vec3(1));
  }
  float nr=0.09*(1.0+0.25*uKick);
  float kk=fract(length(p)/nr*2.0-uT*2.0);
  c=paint(c, L(min(kk,1.0-kk),0.08)*step(length(p),nr*1.6), WHITE()?INK():mix(ac(),vec3(1),0.5));
  return c;
}
// 25 icosahedron wireframe with a counter-rotating inner copy (recursion)
float icosaD(vec2 p, float t, float s){
  const float G=1.618034;
  vec3 v[12];
  v[0]=vec3(-1.0,G,0.0); v[1]=vec3(1.0,G,0.0); v[2]=vec3(-1.0,-G,0.0); v[3]=vec3(1.0,-G,0.0);
  v[4]=vec3(0.0,-1.0,G); v[5]=vec3(0.0,1.0,G); v[6]=vec3(0.0,-1.0,-G); v[7]=vec3(0.0,1.0,-G);
  v[8]=vec3(G,0.0,-1.0); v[9]=vec3(G,0.0,1.0); v[10]=vec3(-G,0.0,-1.0); v[11]=vec3(-G,0.0,1.0);
  vec2 pr[12];
  for(int i=0;i<12;i++){
    vec3 q=v[i]; q.xz=rot(t)*q.xz; q.yz=rot(t*0.63)*q.yz;
    pr[i]=q.xy/(4.2-q.z*0.6)*s;
  }
  float d=1e9;
  for(int i=0;i<12;i++){ for(int j=i+1;j<12;j++){ if(distance(v[i],v[j])<2.1) d=min(d, segD(p,pr[i],pr[j])); } }
  return d;
}
vec3 lIcosa(vec2 p){
  vec3 c=BG();
  float s=uPrm.x*2.6*(1.0+0.05*uKick);
  float d=icosaD(p, uT*0.5, s);
  if(!WHITE()) c+=ac()*exp(-d*30.0)*0.4;
  c=paint(c, L(d,0.005), WHITE()?ac():mix(ac(),vec3(1),0.35));
  if(uPrm.z>0.5){
    float d2=icosaD(p, -uT*0.8+1.0, s*0.42);
    c=paint(c, L(d2,0.004), WHITE()?INK():vec3(1));
  }
  return c;
}

vec3 scene(int id, vec2 p){
  if(id==0) return lWeave(p);
  if(id==1) return lTunnel(p);
  if(id==2) return lRoom(p);
  if(id==3) return lTesseract(p);
  if(id==4) return lStripeSphere(p);
  if(id==5) return lDashSphere(p);
  if(id==6) return lWormhole(p);
  if(id==7) return lIsoCubes(p);
  if(id==8) return lBurst(p);
  if(id==9) return lDots(p);
  if(id==10) return lZigzag(p);
  if(id==11) return lLasers(p);
  if(id==12) return lRidges(p);
  if(id==13) return lSilhouette(p);
  if(id==14) return lCubes(p);
  if(id==15) return lGlobe(p);
  if(id==16) return lTerrain(p);
  if(id==17) return lVortex(p);
  if(id==18) return lHarmono(p);
  if(id==19) return lPolyTunnel(p);
  if(id==20) return lStrings(p);
  if(id==21) return lHelix(p);
  if(id==22) return lRain(p);
  if(id==23) return lTopo(p);
  if(id==24) return lOrbits(p);
  return lIcosa(p);
}

void main(){
  vec2 p=(gl_FragCoord.xy-0.5*uRes)/(0.5*uRes.x);
  p=rot(uRot)*p/uZoom;
  fragColor=vec4(clamp(scene(SCENE,p),0.0,1.0),1.0);
}
