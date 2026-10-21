// Composite pass: scene A/B transition + 2D overlay + post FX.
precision highp float;
uniform sampler2D uA, uB, uOv;
uniform vec2 uRes;
uniform float uP;        // transition progress 0..1, <0 = none
uniform float uSeed, uFrame, uTime;
uniform float uPunch;    // zoom punch amount (beat)
uniform float uRGB;      // chromatic split
uniform vec2 uShake;
uniform float uInvert;   // 0..1
uniform float uFlash;    // 0..1 (tinted, not white strobe)
uniform vec3 uFlashCol;
uniform float uGrain, uScan, uVig, uHue, uGlitch, uBarrel, uPixel;
uniform int uMirror;
uniform float uOvFx;     // how much fx the overlay receives
uniform vec4 uOvBands0, uOvBands1; // up to 4 vertical uv bands (y0,y1) that contain overlay pixels
in vec2 vUV;
out vec4 fragColor;

#define PI 3.14159265
float h21(vec2 p){ p=fract(p*vec2(233.34,851.73)+uSeed); p+=dot(p,p+23.45); return fract(p.x*p.y); }
mat2 rot(float a){ float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }
vec3 hueShift(vec3 c, float a){
  const vec3 k=vec3(0.57735);
  float ca=cos(a);
  return c*ca + cross(k,c)*sin(a) + k*dot(k,c)*(1.0-ca);
}

vec2 mirrorUV(vec2 uv){
  if(uMirror==1){ uv.x = uv.x<0.5 ? uv.x : 1.0-uv.x; }
  else if(uMirror==2){ uv = 0.5-abs(uv-0.5); }
  else if(uMirror==3){ uv.y = uv.y<0.5 ? uv.y : 1.0-uv.y; }
  return uv;
}

vec3 tapRGB(sampler2D s, vec2 uv, vec2 dir, float amt){
  vec3 c;
  c.r=texture(s, uv+dir*amt).r;
  c.g=texture(s, uv).g;
  c.b=texture(s, uv-dir*amt).b;
  return c;
}

vec3 sampleT(sampler2D s, vec2 uv){
  vec2 d=(uv-0.5);
  float amt=uRGB*(0.4+length(d)*1.6);
  return tapRGB(s, uv, normalize(d+1e-5), amt);
}

// zoom blur tap set
vec3 zoomBlur(sampler2D s, vec2 uv, float k){
  vec3 acc=vec3(0.0);
  for(int i=0;i<5;i++){
    float f=1.0-k*float(i)/5.0;
    acc+=texture(s, (uv-0.5)*f+0.5).rgb;
  }
  return acc/5.0;
}

// TT (transition type) is a compile-time #define: SwiftShader runs every branch of a runtime
// if-chain with lane masks, so each transition gets its own small program.
#ifdef TT
vec3 transition(vec2 uv, float p){
  vec2 c=uv-0.5;
  c.y*=uRes.y/uRes.x;
  float r=length(c);
#if TT==0 // hard cut with crunch
    return p<0.5 ? sampleT(uA,uv) : sampleT(uB,uv);
#elif TT==1 // zoom through (recursion)
    float e=p*p*(3.0-2.0*p);
    vec2 ua=(uv-0.5)/(1.0+e*6.0)+0.5;
    vec2 ub=fract((uv-0.5)/(0.2+0.8*e)+0.5); // B arrives as recursive tiles
    vec3 a=zoomBlur(uA,ua,0.25*e);
    vec3 b=zoomBlur(uB,ub,0.25*(1.0-e));
    return mix(a,b,smoothstep(0.35,0.65,p));
#elif TT==2 // iris / pupil
    float rad=p*1.25;
    float edge=smoothstep(rad, rad-0.015, r);
    vec2 ua=uv+normalize(c+1e-5)*0.05*p*sin(r*40.0-p*20.0)*0.3;
    vec3 col=mix(sampleT(uA,ua), sampleT(uB,uv), edge);
    float ring=smoothstep(0.03,0.0,abs(r-rad));
    return col+ring*vec3(1.0,0.6,1.0)*0.8;
#elif TT==3 // glitch blocks
    vec2 bs=vec2(8.0,24.0)*(1.0+floor(h21(vec2(floor(uFrame*0.5)))*3.0));
    vec2 bid=floor(uv*bs);
    float n=h21(bid+floor(uFrame*0.5));
    float sel=step(n, p);
    vec2 off=vec2((h21(bid+3.1)-0.5)*0.2*sin(p*PI),0.0);
    vec3 a=tapRGB(uA, uv+off, vec2(1.0,0.0), 0.01);
    vec3 b=tapRGB(uB, uv-off, vec2(1.0,0.0), 0.01);
    return mix(a,b,sel);
#elif TT==4 // swirl
    float ang=sin(p*PI)*6.0*smoothstep(0.9,0.0,r);
    vec2 cc=rot(ang)*c; cc.y*=uRes.x/uRes.y;
    vec2 su=cc+0.5;
    return mix(sampleT(uA,su), sampleT(uB,su), smoothstep(0.4,0.6,p));
#elif TT==5 // kaleido fold
    float seg=floor(mix(1.0,10.0,sin(p*PI)));
    float a=atan(c.y,c.x); float sa=2.0*PI/max(seg,1.0);
    a=mod(a,sa); a=abs(a-sa*0.5);
    vec2 cc=vec2(cos(a),sin(a))*r; cc.y*=uRes.x/uRes.y;
    vec2 ku=mix(uv, cc+0.5, sin(p*PI));
    return mix(sampleT(uA,ku), sampleT(uB,ku), smoothstep(0.45,0.55,p));
#elif TT==6 // melt drip
    float col=floor(uv.x*60.0);
    float d=(0.4+0.6*h21(vec2(col,7.0)))*1.4;
    float fall=p*d*1.6;
    vec2 ua=vec2(uv.x, uv.y+fall); // A drips down, B is revealed from the top
    return mix(sampleT(uA,ua), sampleT(uB,uv), step(1.0, ua.y));
#elif TT==7 // pixelate dissolve
    float px=mix(1.0, 90.0, sin(p*PI));
    vec2 cell=max(vec2(px)/uRes,vec2(1.0)/uRes);
    vec2 pu=(floor(uv/cell)+0.5)*cell;
    return mix(texture(uA,pu).rgb, texture(uB,pu).rgb, smoothstep(0.4,0.6,p));
#elif TT==8 // slit stripes
    float n=24.0;
    float row=floor(uv.y*n);
    float dirS=mod(row,2.0)*2.0-1.0;
    float sh=p*1.2*dirS*(0.6+0.4*h21(vec2(row,2.0)));
    vec2 ua=vec2(uv.x+sh, uv.y);
    vec2 ub=vec2(uv.x+sh-dirS*1.2, uv.y);
    bool inA = ua.x>=0.0 && ua.x<=1.0;
    return inA ? sampleT(uA,ua) : sampleT(uB,fract(ub));
#else // 9 liquid displacement
    vec2 n=vec2(h21(floor(uv*40.0)), h21(floor(uv*40.0)+5.0))-0.5;
    vec2 d=vec2(sin(uv.y*18.0+p*8.0), cos(uv.x*14.0-p*6.0))*0.06*sin(p*PI);
    return mix(sampleT(uA,uv+d), sampleT(uB,uv-d), smoothstep(0.3,0.7,p));
#endif
}
#endif

void main(){
  vec2 uv=vUV;
  // camera fx
  vec2 c=uv-0.5;
  c*=1.0-uPunch;
  c+=uShake;
  if(uBarrel>0.0){ float r2=dot(c,c); c*=1.0+uBarrel*r2*2.0; }
  uv=c+0.5;
  // glitch line displacement
  if(uGlitch>0.0){
    float line=floor(uv.y*120.0);
    float g=h21(vec2(line, floor(uFrame)));
    if(g<uGlitch*0.35) uv.x+=(h21(vec2(line*3.1,uFrame))-0.5)*0.15*uGlitch;
  }
  uv=mirrorUV(uv);
  if(uPixel>1.0){ vec2 cell=vec2(uPixel)/uRes; uv=(floor(uv/cell)+0.5)*cell; }
#ifdef TT
  vec3 col = transition(uv,uP);
#else
  vec3 col = sampleT(uA,uv);
#endif
  // colour fx
  col=hueShift(col,uHue);
  col=mix(col, 1.0-col, uInvert);
  col=mix(col, uFlashCol, uFlash);
  // overlay (2D canvas, premultiplied rgba) — only sampled inside the bands where something was drawn
  vec2 ouv=mix(vUV, uv, uOvFx);
  bool inBand=(ouv.y>=uOvBands0.x&&ouv.y<=uOvBands0.y)||(ouv.y>=uOvBands0.z&&ouv.y<=uOvBands0.w)||
              (ouv.y>=uOvBands1.x&&ouv.y<=uOvBands1.y)||(ouv.y>=uOvBands1.z&&ouv.y<=uOvBands1.w);
  if(inBand){
    vec4 ov=texture(uOv,ouv);
    col=col*(1.0-ov.a)+ov.rgb;
  }
  // film
  float sl=0.5+0.5*sin(vUV.y*uRes.y*1.2);
  col*=1.0-uScan*sl*0.18;
  col+=(h21(vUV*uRes+uFrame)-0.5)*uGrain;
  vec2 vc=vUV-0.5; vc.y*=0.7;
  col*=1.0-uVig*smoothstep(0.25,0.75,length(vc));
  fragColor=vec4(clamp(col,0.0,1.0),1.0);
}
