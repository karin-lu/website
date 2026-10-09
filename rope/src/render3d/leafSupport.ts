import * as THREE from 'three';

type Face = { triangle: THREE.Triangle; uv: THREE.Vector2[]; normal: THREE.Vector3 };

/** Only previously seated leaves can support a later layer. Alpha testing
 * prevents a transparent rectangle around a painted leaf counting as contact. */
export class LeafSupport {
  private cells = new Map<string, Set<Face>>();
  constructor(private opaque?: (uv: THREE.Vector2) => boolean) {}
  add(points: THREE.Vector3[], uvs: THREE.Vector2[]): void {
    const triangle=new THREE.Triangle(...points as [THREE.Vector3,THREE.Vector3,THREE.Vector3]);
    if (triangle.getArea()<1e-10) return;
    const face={triangle,uv:uvs,normal:triangle.getNormal(new THREE.Vector3())};
    const box=new THREE.Box3().setFromPoints(points);
    for (let z=Math.floor(box.min.z/.2);z<=Math.floor(box.max.z/.2);z++)
      for (let y=Math.floor(box.min.y/.2);y<=Math.floor(box.max.y/.2);y++)
        for (let x=Math.floor(box.min.x/.2);x<=Math.floor(box.max.x/.2);x++) {
          const key=`${x},${y},${z}`;
          let cell=this.cells.get(key); if (!cell) this.cells.set(key,cell=new Set()); cell.add(face);
        }
  }
  below(origin: THREE.Vector3, normal: THREE.Vector3, range: number): {point:THREE.Vector3;normal:THREE.Vector3}|undefined {
    const ray=new THREE.Ray(origin,normal.clone().negate()), faces=new Set<Face>();
    const sample=new THREE.Vector3(), point=new THREE.Vector3();
    for (let t=0;t<=range+.001;t+=.08) {
      ray.at(Math.min(t,range),sample);
      const key=[sample.x,sample.y,sample.z].map(v=>Math.floor(v/.2)).join(',');
      for (const face of this.cells.get(key) ?? []) faces.add(face);
    }
    let best=range, result: {point:THREE.Vector3;normal:THREE.Vector3}|undefined;
    for (const face of faces) {
      if (!ray.intersectTriangle(face.triangle.a,face.triangle.b,face.triangle.c,false,point)) continue;
      const distance=point.distanceTo(origin); if (distance>best) continue;
      const bary=face.triangle.getBarycoord(point,new THREE.Vector3())!;
      const uv=new THREE.Vector2(); face.uv.forEach((v,k)=>uv.addScaledVector(v,bary.getComponent(k)));
      if (this.opaque && !this.opaque(uv)) continue;
      const n=face.normal.clone(); if (n.dot(normal)<0) n.negate();
      best=distance; result={point:point.clone(),normal:n};
    }
    return result;
  }
}

export function leafOpacitySampler(material: THREE.MeshStandardMaterial): ((uv:THREE.Vector2)=>boolean)|undefined {
  const texture=material.map, image=texture?.image as (CanvasImageSource & {width:number;height:number})|undefined;
  if (!texture || !image?.width || !image.height) return;
  const canvas=document.createElement('canvas'); canvas.width=image.width; canvas.height=image.height;
  const ctx=canvas.getContext('2d',{willReadFrequently:true}); if (!ctx) return;
  ctx.drawImage(image,0,0); const pixels=ctx.getImageData(0,0,image.width,image.height).data;
  texture.updateMatrix();
  return uv=>{
    const p=texture.transformUv(uv.clone());
    const x=THREE.MathUtils.clamp(Math.floor(p.x*image.width),0,image.width-1);
    const y=THREE.MathUtils.clamp(Math.floor(p.y*image.height),0,image.height-1);
    return pixels[(y*image.width+x)*4+3]!/255>=Math.max(.35,material.alphaTest);
  };
}
