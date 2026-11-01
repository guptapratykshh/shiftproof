import { useResolvedTheme } from "../theme";
import { tr, msg } from "../i18n";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
export default function Scene({ industry }: { industry: string }) {
  const theme = useResolvedTheme();
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFailed(true);
      return;
    }
    setFailed(false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);
    renderer.domElement.setAttribute("aria-hidden", "true");
    renderer.shadowMap.enabled = true;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(8, 7, 10);
    camera.lookAt(0, 0.3, 0);
    scene.add(new THREE.AmbientLight(0xffffff, theme === "dark" ? 1.6 : 2.0));
    const light = new THREE.DirectionalLight(0xffffff, theme === "dark" ? 2.2 : 3);
    light.position.set(4, 8, 3);
    light.castShadow = true;
    scene.add(light);
    const group = new THREE.Group();
    scene.add(group);
    const material = (color: number) =>
      new THREE.MeshStandardMaterial({
        color,
        roughness: 0.65,
        metalness: 0.12,
      });
    const green = material(theme === "dark" ? 0x9b82c2 : 0x352653),
      sage = material(0xb9a4f5),
      orange = material(0x9975da),
      cream = material(theme === "dark" ? 0x827398 : 0xeee8fc),
      dark = material(0x211a30);
    function box(
      w: number,
      h: number,
      d: number,
      x: number,
      y: number,
      z: number,
      m: THREE.Material,
    ) {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
      mesh.position.set(x, y, z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
      return mesh;
    }
    box(7, 0.25, 5, 0, -0.7, 0, cream);
    box(6.5, 0.12, 4.5, 0, -0.5, 0, sage);
    const cubes: THREE.Mesh[] = [];
    if (
      [
        "manufacturing",
        "warehousing",
        "quality_assurance",
        "food_processing",
      ].includes(industry)
    ) {
      box(5, 0.22, 1.35, 0, 0.1, 0.7, green);
      for (let x = -2.4; x <= 2.4; x += 0.4) {
        const roller = new THREE.Mesh(
          new THREE.CylinderGeometry(0.09, 0.09, 1.25, 12),
          cream,
        );
        roller.rotation.x = Math.PI / 2;
        roller.position.set(x, 0.27, 0.7);
        group.add(roller);
      }
      for (const x of [-1.7, 0, 1.7]) {
        cubes.push(
          box(0.85, 0.8, 0.85, x, 0.75, 0.7, x === 0 ? orange : cream),
        );
        box(0.08, 0.015, 0.86, x, 1.16, 0.7, sage);
      }
      if (industry === "warehousing") {
        for (const y of [0.3, 1.3, 2.3]) {
          box(4.8, 0.12, 0.8, 0, y, -1.4, green);
          for (const x of [-1.7, 0, 1.7])
            box(0.8, 0.65, 0.65, x, y + 0.4, -1.4, cream);
        }
        for (const x of [-2.5, 2.5]) box(0.15, 3, 0.8, x, 0.85, -1.4, green);
      } else if (industry === "food_processing") {
        box(3.2, 2.5, 1.4, 0, 0.8, -1.4, cream);
        box(2.6, 1.9, 0.05, 0, 0.9, -0.67, green);
        box(0.12, 0.8, 0.08, 1, 0.9, -0.61, orange);
      } else if (industry === "quality_assurance") {
        box(3, 0.15, 1.3, 0, 0.6, -1.1, cream);
        for (const x of [-1.2, 1.2]) box(0.15, 1.1, 0.15, x, 0, -1.1, green);
        box(0.55, 0.6, 0.55, 0, 1, -1.1, orange);
        const lens = new THREE.Mesh(
          new THREE.TorusGeometry(0.5, 0.1, 12, 40),
          green,
        );
        lens.position.set(0, 1.9, -1);
        group.add(lens);
        box(0.13, 1.1, 0.13, -0.55, 1.2, -1, green);
      } else {
        box(1.7, 2.4, 1.5, -1.6, 0.8, -1.1, green);
        box(1.2, 0.7, 0.1, -1.6, 1.4, -0.29, dark);
        box(0.8, 0.35, 0.12, -1.6, 1.4, -0.21, orange);
        box(1.3, 0.4, 1.2, 1.3, 0.1, -1.1, green);
        box(0.12, 2.5, 0.12, 1.3, 0.8, -1.3, green);
        box(1.4, 0.15, 0.6, 1.3, 2, -1.1, cream);
      }
    } else if (industry === "maintenance" || industry === "facilities") {
      box(3.4, 0.4, 2.1, 0, -0.15, 0, green);
      const motor = new THREE.Mesh(
        new THREE.CylinderGeometry(0.9, 0.9, 2.4, 32),
        sage,
      );
      motor.rotation.z = Math.PI / 2;
      motor.position.y = 0.85;
      group.add(motor);
      for (const x of [-1.3, 1.3]) {
        const wheel = new THREE.Mesh(
          new THREE.TorusGeometry(0.7, 0.13, 12, 32),
          green,
        );
        wheel.rotation.y = Math.PI / 2;
        wheel.position.set(x, 0.85, 0);
        group.add(wheel);
      }
      box(0.7, 0.7, 0.7, 0, 1.9, 0, orange);
      box(0.3, 1.7, 0.3, -2, 0.2, -1, green);
      box(1.7, 0.3, 0.3, -1.3, 1, -1, green);
      if (industry === "facilities")
        for (let i = 0; i < 3; i++)
          box(0.7, 2 + i * 0.4, 0.8, 1.4 - i * 1.2, 0.4, -1.5, cream);
    } else if (industry === "construction") {
      for (const x of [-2, 0, 2])
        for (const z of [-1.4, 1.4]) box(0.2, 3.7, 0.2, x, 1.3, z, green);
      for (const y of [0.1, 1.7, 3.1]) box(4.6, 0.15, 3.4, 0, y, 0, cream);
      box(0.22, 5, 0.22, -2.7, 1.9, -1.8, orange);
      box(5, 0.2, 0.2, -0.5, 4.4, -1.8, orange);
      box(0.04, 2, 0.04, 1.3, 3.4, -1.8, dark);
    } else {
      box(4, 2.5, 2.1, 0, 0.8, -0.7, cream);
      for (const x of [-1.2, 0, 1.2]) box(0.6, 0.65, 0.06, x, 1, -1.78, green);
      box(0.35, 1.1, 0.1, 0, 1.8, 0.41, orange);
      box(1.1, 0.35, 0.1, 0, 1.8, 0.42, orange);
      box(2, 0.25, 1.2, 0, 0.2, 1.2, green);
    }
    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(0.34, 0.07, 12, 48),
      orange,
    );
    halo.position.set(2.3, 2.5, 1.4);
    halo.rotation.y = 0.5;
    group.add(halo);
    let visible = true,
      frame = 0,
      disposed = false;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    function render(t = 0) {
      if (disposed) return;
      if (visible && !document.hidden) {
        if (!reduced.matches) {
          group.rotation.y = Math.sin(t * 0.00016) * 0.08;
          halo.position.y = 2.5 + Math.sin(t * 0.002) * 0.1;
        }
        renderer.render(scene, camera);
      }
      if (!reduced.matches && visible && !document.hidden)
        frame = requestAnimationFrame(render);
    }
    const resize = new ResizeObserver(() => {
      const w = host.clientWidth,
        h = host.clientHeight;
      if (w && h) {
        renderer.setSize(w, h);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.render(scene, camera);
      }
    });
    resize.observe(host);
    const observer = new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      cancelAnimationFrame(frame);
      if (visible) render();
    });
    observer.observe(host);
    const motion = () => {
      cancelAnimationFrame(frame);
      render();
    };
    reduced.addEventListener("change", motion);
    document.addEventListener("visibilitychange", motion);
    render();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      resize.disconnect();
      reduced.removeEventListener("change", motion);
      document.removeEventListener("visibilitychange", motion);
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh) o.geometry.dispose();
      });
      [green, sage, orange, cream, dark].forEach((m) => m.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [industry, theme]);
  return (
    <div
      ref={ref}
      className="industry-scene"
      role="img"
      aria-label={msg("{industry} handover illustration", {
        industry: tr(industry.replaceAll("_", " ")),
      })}
    >
      {failed && (
        <div className="scene-fallback">
          <span>{tr("REPORT")}</span>
          
          <span>{tr("VERIFY")}</span>
          
          <span>{tr("HAND OVER")}</span>
          <p>{tr("An unresolved issue stays visible at every step.")}</p>
        </div>
      )}
    </div>
  );
}
