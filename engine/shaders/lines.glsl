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
  return lRidges(p);
}

void main(){
  vec2 p=(gl_FragCoord.xy-0.5*uRes)/(0.5*uRes.x);
  p=rot(uRot)*p/uZoom;
  fragColor=vec4(clamp(scene(SCENE,p),0.0,1.0),1.0);
}
