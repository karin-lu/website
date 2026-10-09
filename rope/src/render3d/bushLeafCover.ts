import * as THREE from 'three';
import { VineSurface, rand } from './ivySurface';

/** Sample the front of the backing in camera space, then root overlapping
 * fuzzy leaf blades on that surface. This replaces the old rock-root carpet. */
export function buildBushLeafCover(backing: THREE.BufferGeometry, leaves: THREE.BufferGeometry,
  world: THREE.Matrix4): THREE.BufferGeometry {
  const position=backing.getAttribute('position'), normal=backing.getAttribute('normal');
  const normalMatrix=new THREE.Matrix3().getNormalMatrix(world), inverse=world.clone().invert();
  const points: THREE.Vector3[]=[], normals: THREE.Vector3[]=[], soup: number[]=[];
  for (let i=0;i<position.count;i++) {
    const p=new THREE.Vector3().fromBufferAttribute(position,i).applyMatrix4(world);
    points.push(p); p.toArray(soup,soup.length);
    normals.push(new THREE.Vector3().fromBufferAttribute(normal,i).applyMatrix3(normalMatrix).normalize());
  }
  const surface=new VineSurface(soup), box=new THREE.Box3().setFromPoints(points);
  const spacing=.035;
  const front=new Map<string,{point:THREE.Vector3;normal:THREE.Vector3}>();
  for (let i=0;i<points.length;i+=3) {
    const [a,b,c]=points.slice(i,i+3), [na,nb,nc]=normals.slice(i,i+3);
    const denominator=(b.y-c.y)*(a.x-c.x)+(c.x-b.x)*(a.y-c.y);
    if (Math.abs(denominator)<1e-10) continue;
    const x0=Math.ceil((Math.min(a.x,b.x,c.x)-box.min.x)/spacing), x1=Math.floor((Math.max(a.x,b.x,c.x)-box.min.x)/spacing);
    const y0=Math.ceil((Math.min(a.y,b.y,c.y)-box.min.y)/spacing), y1=Math.floor((Math.max(a.y,b.y,c.y)-box.min.y)/spacing);
    for (let y=y0;y<=y1;y++) for (let x=x0;x<=x1;x++) {
      const px=box.min.x+x*spacing, py=box.min.y+y*spacing;
      const wa=((b.y-c.y)*(px-c.x)+(c.x-b.x)*(py-c.y))/denominator;
      const wb=((c.y-a.y)*(px-c.x)+(a.x-c.x)*(py-c.y))/denominator, wc=1-wa-wb;
      if (Math.min(wa,wb,wc)<-1e-5) continue;
      const p=a.clone().multiplyScalar(wa).addScaledVector(b,wb).addScaledVector(c,wc);
      const n=na.clone().multiplyScalar(wa).addScaledVector(nb,wb).addScaledVector(nc,wc).normalize();
      if (n.z<.05) continue;
      const key=`${x},${y}`, previous=front.get(key);
      if (!previous || previous.point.z<p.z) front.set(key,{point:p,normal:n});
    }
  }
  const tint=new THREE.Color(0,0,0);
  const sites=leaves.userData.ivySupportSites as {colour:number[]}[];
  for (const site of sites) tint.add(new THREE.Color().fromArray(site.colour));
  tint.multiplyScalar(1/sites.length);
  const positions:number[]=[], colours:number[]=[], uvs:number[]=[], indices:number[]=[], roots:number[][]=[];
  let card=0;
  for (const target of front.values()) {
    const angle=(rand(7723,card,1)-.5)*1.2;
    const up=new THREE.Vector3(Math.sin(angle),Math.cos(angle),0), right=new THREE.Vector3(up.y,-up.x,0);
    const width=.13+.025*rand(7723,card,2), height=.135+.025*rand(7723,card,3);
    const root=surface.nearest(target.point.clone().addScaledVector(up,-height*.41))!;
    const anchor=root.point.clone().addScaledVector(root.normal,.006);
    roots.push(anchor.toArray());
    const cell=Math.floor(rand(7723,card,4)*15), u0=(cell%4)*.25+.03, v0=Math.floor(cell/4)*.25+.03;
    const start=positions.length/3, rows=[0,.09,.4,.7,1];
    for (const s of rows) for (const u of [0,.5,1]) {
      const t=Math.max(0,(s-.09)/.91);
      const p=target.point.clone().addScaledVector(right,(u-.5)*width).addScaledVector(up,(s-.5)*height);
      // Roots actually touch the blob; blades curve toward the camera and
      // overlap their neighbours so the backing cannot form an exposed band.
      p.lerp(anchor,Math.max(0,1-t*3));
      if (t>0) p.z+=.010+.018*Math.sin(Math.PI*t);
      surface.project(p,.006);
      p.applyMatrix4(inverse); positions.push(p.x,p.y,p.z);
      uvs.push(u0+u*.19,v0+(1-s)*.19);
      const shade=.96+.09*t+.035*rand(7723,Math.floor(card/8),5);
      colours.push(tint.r*shade,tint.g*shade,tint.b*shade);
    }
    for (let r=0;r<4;r++) for (let col=0;col<2;col++) {
      const i=start+r*3+col;
      const face=[i,i+1,i+4,i,i+4,i+3];
      if (world.determinant()<0) for (let j=0;j<6;j+=3) [face[j+1],face[j+2]]=[face[j+2]!,face[j+1]!];
      indices.push(...face);
    }
    card++;
  }
  const result=new THREE.BufferGeometry();
  result.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  result.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));
  result.setAttribute('color',new THREE.Float32BufferAttribute(colours,3));
  result.setIndex(indices); result.computeVertexNormals(); result.computeBoundingBox(); result.computeBoundingSphere();
  result.userData.cameraCoverCards=card; result.userData.bushLeafRoots=roots;
  return result;
}
